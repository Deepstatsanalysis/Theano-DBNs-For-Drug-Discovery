"""
**************************************************************************
Theano Deep Belief Networks

A Pyramidal Multitask Neural Network (P-MTNN [2000, 100])
**************************************************************************

@author: Jason Feriante <feriante@cs.wisc.edu>
@date: 20 July 2015
"""

import os, sys, timeit, numpy, theano, time, cPickle
import theano.tensor as T
from theano.sandbox.rng_mrg import MRG_RandomStreams

# lib.theano: our local versions of things (some key things are modified)
from lib.theano.multitask_sgd import MultitaskLogReg
from lib.theano.mlp import HiddenLayer
from lib.theano.rbm import RBM
# helpers is not a theano library
from lib.theano import helpers


# start-snippet-1
class DBN_multi(object):
    """Deep Belief Network

    A deep belief network is obtained by stacking several RBMs on top of each
    other. The hidden layer of the RBM at layer `i` becomes the input of the
    RBM at layer `i+1`. The first layer RBM gets as input the input of the
    network, and the hidden layer of the last RBM represents the output. When
    used for classification, the DBN is treated as a MLP, by adding a logistic
    regression layer on top.
    """

    def __init__(self, numpy_rng, theano_rng=None, n_ins=784,
                 hidden_layers_sizes=[500, 500], n_outs=10, num_tasks=1):
        """This class is made to support a variable number of layers.

        :type numpy_rng: numpy.random.RandomState
        :param numpy_rng: numpy random number generator used to draw initial
                    weights

        :type theano_rng: theano.tensor.shared_randomstreams.RandomStreams
        :param theano_rng: Theano random generator; if None is given one is
                           generated based on a seed drawn from `rng`

        :type n_ins: int
        :param n_ins: dimension of the input to the DBN

        :type hidden_layers_sizes: list of ints
        :param hidden_layers_sizes: intermediate layers size, must contain
                               at least one value

        :type n_outs: int
        :param n_outs: dimension of the output of the network

        :type num_tasks: int
        :param num_tasks: the number of separate multitask targets which will
        be evaluated. This also represents the number of separate 
        logistic regression subclasses multitask logistic regression will need
        to spawn 

        """

        self.sigmoid_layers = []
        self.rbm_layers = []
        self.params = []
        self.n_layers = len(hidden_layers_sizes)

        assert self.n_layers > 0

        if not theano_rng:
            theano_rng = MRG_RandomStreams(numpy_rng.randint(2 ** 30))

        # allocate symbolic variables for the data
        self.x = T.matrix('x')  # the data is presented 1024 bit strings
        self.y = T.matrix('y')  # the labels are presented as a matrix
        self.y = T.cast(self.y, 'int32')

        # end-snippet-1
        # The DBN is an MLP, for which all weights of intermediate
        # layers are shared with a different RBM.  We will first
        # construct the DBN as a deep multilayer perceptron, and when
        # constructing each sigmoidal layer we also construct an RBM
        # that shares weights with that layer. During pretraining we
        # will train these RBMs (which will lead to chainging the
        # weights of the MLP as well) During finetuning we will finish
        # training the DBN by doing stochastic gradient descent on the
        # MLP.

        for i in xrange(self.n_layers):
            # construct the sigmoidal layer

            # the size of the input is either the number of hidden
            # units of the layer below or the input size if we are on
            # the first layer
            if i == 0:
                input_size = n_ins
            else:
                input_size = hidden_layers_sizes[i - 1]

            # the input to this layer is either the activation of the
            # hidden layer below or the input of the DBN if you are on
            # the first layer
            if i == 0:
                layer_input = self.x
            else:
                layer_input = self.sigmoid_layers[-1].output

            sigmoid_layer = HiddenLayer(rng=numpy_rng,
                                        input=layer_input,
                                        n_in=input_size,
                                        n_out=hidden_layers_sizes[i],
                                        activation=T.nnet.sigmoid)

            # add the layer to our list of layers
            self.sigmoid_layers.append(sigmoid_layer)

            # its arguably a philosophical question...  but we are
            # going to only declare that the parameters of the
            # sigmoid_layers are parameters of the DBN. The visible
            # biases in the RBM are parameters of those RBMs, but not
            # of the DBN.
            self.params.extend(sigmoid_layer.params)

            # Construct an RBM that shared weights with this layer
            rbm_layer = RBM(numpy_rng=numpy_rng,
                            theano_rng=theano_rng,
                            input=layer_input,
                            n_visible=input_size,
                            n_hidden=hidden_layers_sizes[i],
                            W=sigmoid_layer.W,
                            hbias=sigmoid_layer.b)
            self.rbm_layers.append(rbm_layer)

        # We now need to add a logistic layer on top of the MLP
        self.multiLogLayer = MultitaskLogReg(
            input=self.sigmoid_layers[-1].output,
            n_in=hidden_layers_sizes[-1],
            n_out=n_outs, num_tasks=num_tasks)


        # for i in range(num_tasks):
        #     self.params.extend(self.multiLogLayer.multi['LogLayer' + str(i)])


        # compute the cost for second phase of training, defined as the
        # negative log likelihood of the logistic regression (output) layer
        self.finetune_cost = self.multiLogLayer.negative_log_likelihood(self.y, num_tasks)

        # compute the gradients with respect to the model parameters
        # symbolic variable that points to the number of errors made on the
        # minibatch given by self.x and self.y
        self.errors = self.multiLogLayer.errors(self.y, num_tasks)

    def pretraining_functions(self, train_set_x, batch_size, k):
        '''Generates a list of functions, for performing one step of
        gradient descent at a given layer. The function will require
        as input the minibatch index, and to train an RBM you just
        need to iterate, calling the corresponding function on all
        minibatch indexes.

        :type train_set_x: theano.tensor.TensorType
        :param train_set_x: Shared var. that contains all datapoints used
                            for training the RBM
        :type batch_size: int
        :param batch_size: size of a [mini]batch
        :param k: number of Gibbs steps to do in CD-k / PCD-k

        '''

        # index to a [mini]batch
        index = T.lscalar('index')  # index to a minibatch
        learning_rate = T.scalar('lr')  # learning rate to use

        # number of batches
        n_batches = train_set_x.get_value(borrow=True).shape[0] / batch_size
        # begining of a batch, given `index`
        batch_begin = index * batch_size
        # ending of a batch given `index`
        batch_end = batch_begin + batch_size

        pretrain_fns = []
        for rbm in self.rbm_layers:

            # get the cost and the updates list
            # using CD-k here (persisent=None) for training each RBM.
            # TODO: change cost function to reconstruction error
            cost, updates = rbm.get_cost_updates(learning_rate,
                                                 persistent=None, k=k)

            # compile the theano function
            fn = theano.function(
                inputs=[index, theano.Param(learning_rate, default=0.1)],
                outputs=cost,
                updates=updates,
                givens={
                    self.x: train_set_x[batch_begin:batch_end]
                }
            )
            # append `fn` to the list of functions
            pretrain_fns.append(fn)

        return pretrain_fns

    def build_finetune_functions(self, datasets, batch_size, learning_rate):
        '''Generates a function `train` that implements one step of
        finetuning, a function `validate` that computes the error on a
        batch from the validation set, and a function `test` that
        computes the error on a batch from the testing set

        :type datasets: list of pairs of theano.tensor.TensorType
        :param datasets: It is a list that contain all the datasets;
                        the has to contain three pairs, `train`,
                        `valid`, `test` in this order, where each pair
                        is formed of two Theano variables, one for the
                        datapoints, the other for the labels
        :type batch_size: int
        :param batch_size: size of a minibatch
        :type learning_rate: float
        :param learning_rate: learning rate used during finetune stage

        '''

        (train_set_x, train_set_y) = datasets[0]
        (valid_set_x, valid_set_y) = datasets[1]
        (test_set_x, test_set_y) = datasets[2]


        # compute number of minibatches for training, validation and testing
        n_valid_batches = valid_set_x.get_value(borrow=True).shape[0]
        n_valid_batches /= batch_size
        n_test_batches = test_set_x.get_value(borrow=True).shape[0]
        n_test_batches /= batch_size

        index = T.lscalar('index')  # index to a [mini]batch

        # compute the gradients with respect to the model parameters
        gparams = T.grad(self.finetune_cost, self.params)

        # compute list of fine-tuning updates
        updates = []
        for param, gparam in zip(self.params, gparams):
            updates.append((param, param - gparam * learning_rate))


        train_fn = theano.function(
            inputs=[index],
            outputs=self.finetune_cost,
            updates=updates,
            givens={
                self.x: train_set_x[
                    index * batch_size: (index + 1) * batch_size
                ],
                self.y: train_set_y[
                    index * batch_size: (index + 1) * batch_size
                ]
            }
        )

        test_score_i = theano.function(
            [index],
            self.errors,
            givens={
                self.x: test_set_x[
                    index * batch_size: (index + 1) * batch_size
                ],
                self.y: test_set_y[
                    index * batch_size: (index + 1) * batch_size
                ]
            }
        )

        valid_score_i = theano.function(
            [index],
            self.errors,
            givens={
                self.x: valid_set_x[
                    index * batch_size: (index + 1) * batch_size
                ],
                self.y: valid_set_y[
                    index * batch_size: (index + 1) * batch_size
                ]
            }
        )

        # Create a function that scans the entire validation set
        def valid_score():
            return [valid_score_i(i) for i in xrange(n_valid_batches)]

        # Create a function that scans the entire test set
        def test_score():
            return [test_score_i(i) for i in xrange(n_test_batches)]

        return train_fn, valid_score, test_score


def run_DBN_multi(finetune_lr=0.1, pretraining_epochs=100,
             pretrain_lr=0.01, k=1, training_epochs=1000,
             batch_size=100, data_type='', patience=5000):
    """
    Demonstrates how to train and test a Deep Belief Network.

    This is demonstrated on MNIST.

    :type finetune_lr: float
    :param finetune_lr: learning rate used in the finetune stage
    :type pretraining_epochs: int
    :param pretraining_epochs: number of epoch to do pretraining
    :type pretrain_lr: float
    :param pretrain_lr: learning rate to be used during pre-training
    :type k: int
    :param k: number of Gibbs steps in CD/PCD
    :type training_epochs: int
    :param training_epochs: maximal number of iterations ot run the optimizer
    :type dataset: string
    :param dataset: path the the pickled dataset
    :type batch_size: int
    :param batch_size: the size of a minibatch
    """

    # make sure we have something to do
    assert(len(data_type)> 0)

    fold_path = helpers.get_multitask_path(data_type)
    fnames = helpers.build_multi_list(fold_path, data_type)

    fold_accuracies = {}
    did_something = False

    avg_acc = [] # what is our average accuracy %?
    avg_auc = [] # what is our average AUC (based on ROC)?

    # XXXXXXXXXXXXXXX @TODO: convert this too a 5-fold loop)
    test_fold = 0 #xxxxxxxxxxxx TEMP XXXXXXXXXXXXXXXX
    valid_fold = 1 #xxxxxxxxxxxx TEMP XXXXXXXXXXXXXXXX

    # pickle everything -- this will take a while.
    # for fname in fnames:
    #     # Load one file
    #     num_labels, datasets, test_set_labels = helpers.th_load_multi(data_type, fold_path, fname, test_fold, valid_fold)

    #     print 'creating data file: ' + fold_path + '/pkd_' + fname
    #     with open(fold_path + '/pkd_' + fname, 'w') as f:
    #         cPickle.dump(datasets, f)

    #     print 'creating label file: ' + fold_path + '/pkl_' + fname
    #     with open(fold_path + '/pkl_' + fname, 'w') as f:
    #         cPickle.dump(test_set_labels, f)



    # XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX REMOVE XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    # enable lines above / remove this line..... (temp)
    # num_labels, datasets, test_set_labels = helpers.th_load_multi_raw(data_type, fold_path, fnames[0], test_fold, valid_fold)
    num_labels, datasets, test_set_labels = helpers.th_load_multi(data_type, fold_path, fnames[0], test_fold, valid_fold)
    fnames = [fnames[0]]
    train_set_x, train_set_y = datasets[0]
    valid_set_x, valid_set_y = datasets[1]
    test_set_x, test_set_y = datasets[2]

    # XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX REMOVE XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX


    # numpy random generator
    numpy_rng = numpy.random.RandomState(123)

    print '... building the model'
    # construct the Deep Belief Network
    dbn = DBN_multi(numpy_rng=numpy_rng, n_ins=1024 * 1,
              hidden_layers_sizes=[2000, 100],
              n_outs=2, num_tasks=num_labels) #num_tasks = number of targets


    # # start-snippet-2
    # #########################
    # # PRETRAINING THE MODEL #
    # #########################
    # print '... getting the pretraining functions'
    # print '... pre-training the model'
    # start_time = timeit.default_timer()
    # ## Pre-train layer-wise
    # for fname in fnames:

    #     print '... loading ' + fname

    #     # load our relevant pickled data / labels
    #     datasets = cPickle.load(open(fold_path + '/pkd_' + fname))
    #     test_set_labels = cPickle.load(open(fold_path + '/pkl_' + fname))
    #     train_set_x, train_set_y = datasets[0]
    #     valid_set_x, valid_set_y = datasets[1]
    #     test_set_x, test_set_y = datasets[2]

    #     # compute number of minibatches for training, validation and testing
    #     n_train_batches = train_set_x.get_value(borrow=True).shape[0] / batch_size
    #     pretraining_fns = dbn.pretraining_functions(train_set_x=train_set_x,
    #                                                 batch_size=batch_size,
    #                                                 k=k)

    #     for i in xrange(dbn.n_layers):
    #         # go through pretraining epochs
    #         for epoch in xrange(pretraining_epochs):
    #             # go through the training set
    #             c = []
    #             for batch_index in xrange(n_train_batches):
    #                 c.append(pretraining_fns[i](index=batch_index,
    #                                             lr=pretrain_lr))
    #             print 'Pre-training layer %i, epoch %d, cost ' % (i, epoch),
    #             print numpy.mean(c)

    # end_time = timeit.default_timer()
    # # end-snippet-2
    # print >> sys.stderr, ('The pretraining code for file ' +
    #                       os.path.split(__file__)[1] +
    #                       ' ran for %.2fm' % ((end_time - start_time) / 60.))
    ########################
    # FINETUNING THE MODEL #
    ########################


    # get the training, validation and testing function for the model
    print '... getting the finetuning functions'
    train_fn, validate_model, test_model = dbn.build_finetune_functions(
        datasets=datasets,
        batch_size=batch_size,
        learning_rate=finetune_lr
    )

    print '... finetuning the model'
    # early-stopping parameters
    patience = 30 * n_train_batches  # look as this many examples regardless
    patience_increase = 2.0   # wait this much longer when a new best is found
    improvement_threshold = 0.995  # a relative improvement of this much is
                                   # considered significant
    validation_frequency = min(n_train_batches, patience / 2)
                                  # go through this many
                                  # minibatches before checking the network
                                  # on the validation set; in this case we
                                  # check every epoch

    best_validation_loss = numpy.inf
    test_score = 0.
    start_time = timeit.default_timer()

    done_looping = False
    epoch = 0
    auc = 0
    best_auc = 0
    while (epoch < training_epochs) and (not done_looping):
        epoch = epoch + 1
        for minibatch_index in xrange(n_train_batches):

            minibatch_avg_cost = train_fn(minibatch_index)
            iter = (epoch - 1) * n_train_batches + minibatch_index

            if (iter + 1) % validation_frequency == 0:

                validation_losses = validate_model()
                this_validation_loss = numpy.mean(validation_losses)
                print(
                    'epoch %i, minibatch %i/%i, validation error %f %%'
                    % (
                        epoch,
                        minibatch_index + 1,
                        n_train_batches,
                        this_validation_loss * 100.
                    )
                )

                # get the ROC / AUC 
                auc = helpers.th_calc_auc(dbn, test_set_labels, test_set_x)
                if(auc > best_auc and best_auc > 0):

                    #improve patience if loss improvement is good enough
                    if (
                        auc > best_auc *
                        improvement_threshold
                    ):
                        patience = max(patience, iter * patience_increase)
                        # print 'increased patience!!! (for AUC)'

                    best_auc = auc
                    print '     new best AUC!: ' + str(auc)
                elif(auc > best_auc):
                    best_auc = auc


                # !!!!!!!! @todo: this needs to be based on AUC, not raw accuracy
                # if we got the best validation score until now
                if this_validation_loss < best_validation_loss:

                    #improve patience if loss improvement is good enough
                    if (
                        this_validation_loss < best_validation_loss *
                        improvement_threshold
                    ):
                        patience = max(patience, iter * patience_increase)

                    # save best validation score and iteration number
                    best_validation_loss = this_validation_loss
                    best_iter = iter

                    # test it on the test set
                    test_losses = test_model()
                    test_score = numpy.mean(test_losses)


                    print(('     epoch %i, minibatch %i/%i, best error %f %%, best_auc: %f') %
                          (epoch, minibatch_index + 1, n_train_batches, test_score * 100., best_auc))

            if patience <= iter:
                done_looping = True
                break

    end_time = timeit.default_timer()
    print(
        (
            'Optimization complete with best validation score of %f %%, '
            'obtained at iteration %i, '
            'with test performance %f %%, and best_auc: %f'
        ) % (best_validation_loss * 100., best_iter + 1, test_score * 100., best_auc)
    )
    print >> sys.stderr, ('The fine tuning code for file ' +
                          os.path.split(__file__)[1] +
                          ' ran for %.2fm' % ((end_time - start_time)
                                              / 60.))



def run_predictions(data_type, p_epochs, t_epochs, f_lr, p_lr):

    """ Run the Theano DBN Model """
    run_DBN_multi(pretraining_epochs=p_epochs, training_epochs=t_epochs, 
        data_type=data_type, finetune_lr=f_lr, 
        pretrain_lr=p_lr, patience=2000)



def main(args):


    # !!! Important !!! This has a major impact on the results.
    p_epochs = 8 #default 100 pretraining_epochs
    t_epochs = 500 #default 1000 training_epochs
    f_lr = 0.1 # fine_tune learning rate
    p_lr = 0.01 # unserupvised pre-training learning rate

    if(len(args) < 2):
        print 'usage: <tox21, dud_e, muv, or pcba> <target> '
        return

    dataset = args[1]

    # in case of typos
    if(dataset == 'dude'):
        dataset = 'dud_e'



    print "Running Theano Learn Deep Belief Net for " + dataset


    # settings specific to any particular dataset can go here 
    if(dataset == 'tox21'):

        #  2 p_epochs at p_lr = 0.01: broken
            p_epochs = 1 #default 100 pretraining_epochs
            t_epochs = 1000 #default 1000 training_epochs
            f_lr = 0.1 # fine_tune learning rate
            p_lr = 0.01 # unserupvised pre-training learning rate
            run_predictions('Tox21', p_epochs, t_epochs, f_lr, p_lr) # patience = 2000

    elif(dataset == 'dud_e'):

        run_predictions('DUD-E', 2, t_epochs, f_lr, p_lr)

    elif(dataset == 'muv'):

        run_predictions('MUV', 4, t_epochs, f_lr, 0.04) # patience = 4000

    elif(dataset == 'pcba'):

            p_epochs = 100
            t_epochs = 1000
            f_lr = 0.1
            p_lr = 0.001
            run_predictions('PCBA', p_epochs, t_epochs, f_lr, p_lr)

    else:
        print 'dataset param not found. options: tox21, dud_e, muv, or pcba'



if __name__ == '__main__':
    start_time = time.clock()

    main(sys.argv)

    end_time = time.clock()
    print 'runtime: %.2f secs.' % (end_time - start_time)

    