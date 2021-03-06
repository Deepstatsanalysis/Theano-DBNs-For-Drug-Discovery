"""
**************************************************************************
Helper functions. Requred by both our scikit learn & theano scripts
**************************************************************************

@author: Jason Feriante <feriante@cs.wisc.edu>
@date: 10 July 2015
"""

import generate_folds, os, sys, random, time, theano
import theano.tensor as T
import numpy as np
from sklearn import linear_model
from sklearn import metrics


fold_paths = [
    "./folds/DUD-E",
    "./folds/MUV",
    "./folds/Tox21",
    "./folds/PCBA",
    ]

multitask_paths = [
    "./multitask/DUD-E",
    "./multitask/MUV",
    "./multitask/Tox21",
    "./multitask/PCBA",
    ]

def is_numeric(x):
    try:
        float(x)
        return True
    except ValueError:
        return False
    except TypeError:
        return False


def get_fold_path(data_type):

    if(data_type == 'DUD-E'):
        return fold_paths[0]

    if(data_type == 'MUV'):
        return fold_paths[1]

    if(data_type == 'Tox21'):
        return fold_paths[2]

    if(data_type == 'PCBA'):
        return fold_paths[3]

    raise ValueError('data_type does not exist:' + str(data_type))



def get_multitask_path(data_type):

    if(data_type == 'DUD-E'):
        return multitask_paths[0]

    if(data_type == 'MUV'):
        return multitask_paths[1]

    if(data_type == 'Tox21'):
        return multitask_paths[2]

    if(data_type == 'PCBA'):
        return multitask_paths[3]

    raise ValueError('data_type does not exist:' + str(data_type))


    
def get_target(fname, data_type):
    return generate_folds.get_target(fname, data_type)



def parse_line(line, data_type):

    # row format: [hash_id, is_active, native_id, fold, bitstring]
    parts = line.rstrip('\n').split(r' ')
    # hash_id = parts[0]

    # cast the string to int
    is_active = int(parts[1])

    # native_id = parts[2]
    fold = parts[3]
    bitstring = parts[4]

    return fold, [bitstring, is_active]



def parse_line_multi(line):

    # row format: [hash_id, is_active, native_id, fold, bitstring]
    parts = line.rstrip('\n').split(r' fl')
    bitstring = parts[0]

    parts = parts[1].rstrip('\n').split(r' ')
    fold = int(parts[0])

    # cast labels to int
    labels = parts[1:]
    labels = [int(i) for i in labels]

    return fold, [bitstring, labels]

def num_labels_multi(line):

    # row format: [hash_id, is_active, native_id, fold, bitstring]
    parts = line.rstrip('\n').split(r' fl')
    bitstring = parts[0]

    parts = parts[1].rstrip('\n').split(r' ')

    # cast labels to int
    labels = parts[1:]

    return len(labels)

def get_col_index(target, target_cols):
    """return the column index for this target"""

    for i in range(len(target_cols)):
        if(target == target_cols[i]):
            return i

    # this should never happen
    raise ValueError('get_col_index can\'t find ' + str(target) + '!');



def get_rev_targets(data_type):
    """ for the hashmap generating function; only includes actives """
    """ builds object for each target with fname / col_id """


    fold_path = get_fold_path(data_type)
    target_columns = get_target_list(data_type)

    # init targets
    targets = {}
    rev_targets = {}
    for dir_name, sub, files in os.walk(fold_path):
        for fname in files:
            if fname.startswith('.'):
                # ignore system files
                pass
            else:
                target = get_target(fname, data_type)

                # store the filename & column index for this target
                targets[target] = {'fname': '', 'col_id': -1}
                # print "file:" + fname + ", target:" + target

        for fname in files:
            if fname.startswith('.') or 'inactives' in fname:
                # ignore system files & inactives
                pass
            else:
                target = get_target(fname, data_type)
                col_id = get_col_index(target, target_columns)
                targets[target]['fname'] = fname
                targets[target]['col_id'] = col_id
                # print "file:" + fname + ", target:" + target
                rev_targets[col_id] = {'target':target, 'fname':fname}
                
    
    return rev_targets, target_columns



def load_hashmap(data_type):
    """Load a hashmap into memory"""
    hashmap_path = 'hashmaps/' + data_type + '.hm'

    hashmap = {}
    with open(hashmap_path) as f:
        lines = f.readlines()
        for line in lines:
            # put each row in it's respective fold
            parts = line.rstrip('\n').split(r' ')

            bitstring = parts[0]
            row = parts[1:]

            hashmap[bitstring] = row

    return hashmap

def load_string_col_hashmap(data_type, count = False):
    """Load a hashmap into memory -- but keep the columns in string format"""
    """If a count is passed in, then the first n columns will be loaded and"""
    """the rest will not be included"""
    hashmap_path = 'hashmaps/' + data_type + '.hm'

    if(count == False):
        hashmap = {}
        with open(hashmap_path) as f:
            lines = f.readlines()
            for line in lines:
                # put each row in it's respective fold
                parts = line.rstrip('\n').split(r' ')

                bitstring = parts[0]
                row = parts[1:]
                row = ' '.join(str(v) for v in row)

                hashmap[bitstring] = row

    if(is_numeric(count) and count > 0):
        hashmap = {}
        with open(hashmap_path) as f:
            lines = f.readlines()
            for line in lines:
                # put each row in it's respective fold
                parts = line.rstrip('\n').split(r' ')

                bitstring = parts[0]
                # truncate the column since the entire set of labels is not
                # required for this task
                row = parts[1:count + 1]
                row = ' '.join(str(v) for v in row)

                hashmap[bitstring] = row

    return hashmap


def build_targets(fold_path, data_type):
    """ first run generate_folds if you don't have them yet """
    """ for building folds or training on the folds """

    # init targets
    targets = {}
    for dir_name, sub, files in os.walk(fold_path):

        # part1: build the target list
        for fname in files:
            if fname.startswith('.'):
                # ignore system files
                pass
            else:
                target = get_target(fname, data_type)
                targets[target] = []
                # print "file:" + fname + ", target:" + target

        # part2: build the file list based on the targets
        for fname in files:
            if fname.startswith('.'):
                # ignore system files
                pass
            else:
                target = get_target(fname, data_type)
                targets[target].append(fname)
                # print "file:" + fname + ", target:" + target
    
    return targets


def build_multi_list(fold_path, data_type):
    """ first run generate_folds if you don't have them yet """
    """ for building folds or training on the folds """

    # init targets
    fnames = []
    for dir_name, sub, files in os.walk(fold_path):

        # build the file list
        for fname in files:
            if fname.startswith('.'):
                # ignore system files
                pass
            else:
                fnames.append(fname)
                # print "file:" + fname + ", target:" + target
    
    return fnames



def oversample(data):
    # balance the number of actives / inactives in the dataset
    actives = []
    inactives = []
    for i in range(len(data)):
        if(int(data[i][1]) == 1):
            actives.append(data[i])
        else:
            inactives.append(data[i])

    total_inactives = len(inactives)
    total_actives = len(actives)
    ratio = total_inactives / total_actives

    if(ratio > 30):
        ratio = 30  # oversampling too much slows things down, & gives 
                    # diminishing returns in terms of AUC.
    else:
        pass

    # oversample_total = ratio * total_actives
    oversamples = []
    for i in range(len(actives)):
        for j in range(ratio):
            oversamples.append(actives[i])

    # print len(oversamples)
    # print total_inactives
    # print len(oversamples + inactives)

    # combine oversampled actives + inactives into one list
    return oversamples + inactives



def get_folds(data_type, fold_path, target, fnames):
    # store folds by target
    folds = {}
    for i in range(5):
        # don't forget -- we are using strings & not integer keys!!!
        folds[i] = []

    #fnames contains all files for this target
    for fname in fnames:
        row = []
        with open(fold_path + '/' + fname) as f:
            lines = f.readlines()
            for line in lines:
                # put each row in it's respective fold
                fold, row = parse_line(line, data_type)
                folds[int(fold)].append(row)

    """ Debug """
    # print "length of all folds"
    # print len(folds)
    # print "length of respective folds"
    # print len(folds[0])
    # print len(folds[1])
    # print len(folds[2])
    # print len(folds[3])
    # print len(folds[4])
    
    # oversample the folds to balance actives / inactives
    for i in range(len(folds)):
        folds[i] = oversample(folds[i])


    # shuffle the folds once upfront
    for i in range(len(folds)):
        random.shuffle(folds[i])

    return folds



def shared_dataset(data_xy, borrow=True):
    """ Function that loads the dataset into shared variables
    The reason we store our dataset in shared variables is to allow Theano to copy it into the GPU memory
    (when code is run on GPU). Since copying data into the GPU is slow, copying a minibatch everytime
    is needed (the default behaviour if the data is not in a shared variable) would lead to a large decrease in performance.
    """
    data_x, data_y = data_xy
    shared_x = theano.shared(np.asarray(data_x, dtype=theano.config.floatX), borrow=borrow)
    shared_y = theano.shared(np.asarray(data_y, dtype=theano.config.floatX), borrow=borrow)
    # When storing data on the GPU it has to be stored as floats therefore we will store the labels as ``floatX`` as well
    # (``shared_y`` does exactly that). But during our computations we need them as ints (we use labels as index, and if they are
    # floats it doesn't make sense) therefore instead of returning  ``shared_y`` we will have to cast it to int. This little hack
    # lets ous get around this issue
    return shared_x, T.cast(shared_y, 'int32')



def build_data_set(fold):
    """ Featurizing 1024 bits is a slow process """
    """ ** Built for Theano ** """
    # build training data
    X = []
    Y = []
    for i in range(len(fold)):
        row = []
        for bit in fold[i][0]:
            row.append(int(bit))
        X.append(row)
        Y.append(int(fold[i][1]))

    X = np.array(X)
    Y = np.array(Y)

    return (X, Y)



def build_multi_data_set(fold):
    """ Featurizing 1024 bits is a slow process """
    """ ** Built for Theano ** """
    # build training data
    X = []
    Y = []
    for i in range(len(fold)):

        row = []
        for bit in fold[i][0]:
            row.append(int(bit))
        X.append(row)

        labels = []
        for label in fold[i][1]:
            labels.append(int(label))
        Y.append(labels)

    X = np.array(X)
    # Y = np.vstack(Y)
    Y = np.array(Y)

    return (X, Y)



def th_calc_auc(dbn, test_set_labels, test_set_x):
    """ *************** build AUC curve *************** """


    test_set = test_set_x.get_value()
    # compile a confidence predictor function
    predict_model = theano.function(inputs=[dbn.x], outputs=[dbn.logLayer.p_y_given_x]) 

    # get the probability of our predictions
    conf_preds = predict_model(test_set[:(test_set.shape[0])])

    conf_predictions = []
    for h in range(len(conf_preds)):
        for i in range(len(conf_preds[h])):
            # ignore the first column; this gives a lower score that seems wrong.
            conf_predictions.append(conf_preds[h][i][1])

    # determine ROC / AUC
    fpr, tpr, thresholds = metrics.roc_curve(test_set_labels, conf_predictions)
    auc = metrics.auc(fpr, tpr) # e.g. 0.855
    
    return auc

def th_load_data(data_type, fold_path, target, fnames, fold_train, fold_test):
    """ Get just 1 test & 1 valid fold to avoid overloading memory """
    """The load_files_for_task module takes the input files for a single task"""
    """The module loads the data from these files into two dictionaries - foldsActive and foldsInactive"""
    """Each dictionary contains five lists: 0 to 4 corresponding to a fold."""

    # sanity checks
    if(fold_train < 0 or fold_train > 4):
        raise ValueError('fold_train = ' + str(fold_train) + \
            '. Oops! fold_train must be between 0 and 4!')

    if(fold_test < 0 or fold_test > 4):
        raise ValueError('fold_test = ' + str(fold_test) + \
            '. Oops! fold_test must be between 0 and 4!')

    if(fold_test  == fold_train):
        raise ValueError('fold_train ('+ str(fold_train) + \
            ') == fold_test ('+ str(fold_train) +')... oops!')

    #fnames contains all files for this target
    train_folds = []
    test_folds = []
    for fname in fnames:
        row = []
        with open(fold_path + '/' + fname) as f:
            lines = f.readlines()
            for line in lines:
                # put each row in it's respective fold
                curr_fold, row = parse_line(line, data_type)
                curr_fold = int(curr_fold)

                if(curr_fold == fold_train):
                    train_folds.append(row)

                if(curr_fold == fold_test):
                    test_folds.append(row)
    
    # oversample the folds to balance actives / inactives
    train_folds = oversample(train_folds)
    test_folds = oversample(test_folds)

    # shuffle the folds once upfront
    random.shuffle(train_folds)
    random.shuffle(test_folds)

    train_x, train_y = build_data_set(train_folds)
    test_x, test_y = build_data_set(test_folds)

    # turn into shared datasets
    train_set = (train_x, train_y)
    test_set = (test_x, test_y)

    train_set_x, train_set_y = shared_dataset(train_set)
    test_set_x, test_set_y = shared_dataset(test_set)
    
    datasets = [(train_set_x, train_set_y), (test_set_x, test_set_y)]

    return datasets, test_y



# almost the same as the function above, this is just to get a validation fold
def th_load_data2(data_type, fold_path, target, fnames, fold_valid, fold_test):
    """ Get just 1 test & 1 valid fold to avoid overloading memory """
    """The load_files_for_task module takes the input files for a single task"""
    """The module loads the data from these files into two dictionaries - foldsActive and foldsInactive"""
    """Each dictionary contains five lists: 0 to 4 corresponding to a fold."""

    #fnames contains all files for this target
    train_folds = []
    valid_folds = []
    test_folds = []
    for fname in fnames:
        row = []
        with open(fold_path + '/' + fname) as f:
            lines = f.readlines()
            for line in lines:
                # put each row in it's respective fold
                curr_fold, row = parse_line(line, data_type)
                curr_fold = int(curr_fold)

                if(curr_fold == fold_test):
                    test_folds.append(row)
                elif(curr_fold == fold_valid):
                    valid_folds.append(row)
                else:
                    train_folds.append(row)
    
    # oversample the folds to balance actives / inactives
    train_folds = oversample(train_folds)
    valid_folds = oversample(valid_folds)
    test_folds = oversample(test_folds)

    # shuffle the folds once upfront
    random.shuffle(train_folds)
    random.shuffle(valid_folds)
    random.shuffle(test_folds)

    train_x, train_y = build_data_set(train_folds)
    valid_x, valid_y = build_data_set(valid_folds)
    test_x, test_y = build_data_set(test_folds)

    # turn into shared datasets
    train_set = (train_x, train_y)
    valid_set = (valid_x, valid_y)
    test_set = (test_x, test_y)

    train_set_x, train_set_y = shared_dataset(train_set)
    valid_set_x, valid_set_y = shared_dataset(valid_set)
    test_set_x, test_set_y = shared_dataset(test_set)

    datasets = [(train_set_x, train_set_y), (valid_set_x, valid_set_y), (test_set_x, test_set_y)]

    return datasets, test_y



# almost the same as the function above, this is just to get a validation fold
def th_load_multi(data_type, fold_path, fname, fold_valid, fold_test):
    """ Get just 1 test & 1 valid fold to avoid overloading memory """
    """The load_files_for_task module takes the input files for a single task"""
    """The module loads the data from these files into two dictionaries - foldsActive and foldsInactive"""
    """Each dictionary contains five lists: 0 to 4 corresponding to a fold."""

    #fnames contains all files for this target
    train_folds = []
    valid_folds = []
    test_folds = []
    row = []
    with open(fold_path + '/' + fname) as f:
        lines = f.readlines()
        for line in lines:
            # put each row in it's respective fold
            curr_fold, row = parse_line_multi(line)

            if(curr_fold == fold_test):
                test_folds.append(row)
            elif(curr_fold == fold_valid):
                valid_folds.append(row)
            else:
                train_folds.append(row)
    

    with open(fold_path + '/' + fname) as f:
        lines = f.readlines()
        num_labels = num_labels_multi(lines[0])

    """multibatch is ALREADY oversampled!  (don't do it again)"""

    # shuffle the folds once upfront
    random.shuffle(train_folds)
    random.shuffle(valid_folds)
    random.shuffle(test_folds)

    train_x, train_y = build_multi_data_set(train_folds)
    valid_x, valid_y = build_multi_data_set(valid_folds)
    test_x, test_y = build_multi_data_set(test_folds)

    # turn into shared datasets
    train_set = (train_x, train_y)
    valid_set = (valid_x, valid_y)
    test_set = (test_x, test_y)

    train_set_x, train_set_y = shared_dataset(train_set)
    valid_set_x, valid_set_y = shared_dataset(valid_set)
    test_set_x, test_set_y = shared_dataset(test_set)

    datasets = [(train_set_x, train_set_y), (valid_set_x, valid_set_y), (test_set_x, test_set_y)]

    return num_labels, datasets, test_y


def th_load_multi_raw(data_type, fold_path, fname, fold_valid, fold_test):
    """ Get just 1 test & 1 valid fold to avoid overloading memory """
    """The load_files_for_task module takes the input files for a single task"""
    """The module loads the data from these files into two dictionaries - foldsActive and foldsInactive"""
    """Each dictionary contains five lists: 0 to 4 corresponding to a fold."""

    #fnames contains all files for this target
    train_folds = []
    valid_folds = []
    test_folds = []
    row = []
    with open(fold_path + '/' + fname) as f:
        lines = f.readlines()
        for line in lines:
            # put each row in it's respective fold
            curr_fold, row = parse_line_multi(line)

            if(curr_fold == fold_test):
                test_folds.append(row)
            elif(curr_fold == fold_valid):
                valid_folds.append(row)
            else:
                train_folds.append(row)
    

    with open(fold_path + '/' + fname) as f:
        lines = f.readlines()
        num_labels = num_labels_multi(lines[0])

    """multibatch is ALREADY oversampled!  (don't do it again)"""

    # shuffle the folds once upfront
    random.shuffle(train_folds)
    random.shuffle(valid_folds)
    random.shuffle(test_folds)

    train_x, train_y = build_multi_data_set(train_folds)
    valid_x, valid_y = build_multi_data_set(valid_folds)
    test_x, test_y = build_multi_data_set(test_folds)

    datasets = [(train_x, train_y), (valid_x, valid_y), (test_x, test_y)]

    return num_labels, datasets, test_y


def get_target_list(data_type):
    """Allows a numeric target to be chosen (instead of strings only)"""
    """Of course the number must be in range... the ranges are as follows:"""
    """MUV: has 17 total targets, 0 to 33"""
    """Tox21: 12 targets; 0 to 11"""
    """DUD-E: 102 targets, 0 to 101"""
    """PCBA: 128 targets, 0 to 127"""
     
    # Note: how to files in a single column in linux: ls | tr '\n' '\n' 

    # MUV: has 17 total targets, 0 to 16
    muv = [
        '466',
        '548',
        '600',
        '644',
        '652',
        '689',
        '692',
        '712',
        '713',
        '733',
        '737',
        '810',
        '832',
        '846',
        '852',
        '858',
        '859',
        ]

    # Tox21:
    # 12 targets; 0 to 11
    tox21 = [
        'nr-ahr',
        'nr-ar-lbd',
        'nr-ar',
        'nr-aromatase',
        'nr-er-lbd',
        'nr-er',
        'nr-ppar-gamma',
        'sr-are',
        'sr-atad5',
        'sr-hse',
        'sr-mmp',
        'sr-p53'
        ]

    # DUD-E: 102 targets, 0 to 101
    dude = [
        'aa2ar',
        'abl1',
        'ace',
        'aces',
        'ada17',
        'ada',
        'adrb1',
        'adrb2',
        'akt1',
        'akt2',
        'aldr',
        'ampc',
        'andr',
        'aofb',
        'bace1',
        'braf',
        'cah2',
        'casp3',
        'cdk2',
        'comt',
        'cp2c9',
        'cp3a4',
        'csf1r',
        'cxcr4',
        'def',
        'dhi1',
        'dpp4',
        'drd3',
        'dyr',
        'egfr',
        'esr1',
        'esr2',
        'fa10',
        'fa7',
        'fabp4',
        'fak1',
        'fgfr1',
        'fkb1a',
        'fnta',
        'fpps',
        'gcr',
        'glcm',
        'gria2',
        'grik1',
        'hdac2',
        'hdac8',
        'hivint',
        'hivpr',
        'hivrt',
        'hmdh',
        'hs90a',
        'hxk4',
        'igf1r',
        'inha',
        'ital',
        'jak2',
        'kif11',
        'kit',
        'kith',
        'kpcb',
        'lck',
        'lkha4',
        'mapk2',
        'mcr',
        'met',
        'mk01',
        'mk10',
        'mk14',
        'mmp13',
        'mp2k1',
        'nos1',
        'nram',
        'pa2ga',
        'parp1',
        'pde5a',
        'pgh1',
        'pgh2',
        'plk1',
        'pnph',
        'ppara',
        'ppard',
        'pparg',
        'prgr',
        'ptn1',
        'pur2',
        'pygm',
        'pyrd',
        'reni',
        'rock1',
        'rxra',
        'sahh',
        'src',
        'tgfr1',
        'thb',
        'thrb',
        'try1',
        'tryb1',
        'tysy',
        'urok',
        'vgfr2',
        'wee1',
        'xiap'
    ]

    # PCBA: 128 targets, 0 to 127
    pcba = [
        'aid1030',
        'aid1379',
        'aid1452',
        'aid1454',
        'aid1457',
        'aid1458',
        'aid1460',
        'aid1461',
        'aid1468',
        'aid1469',
        'aid1471',
        'aid1479',
        'aid1631',
        'aid1634',
        'aid1688',
        'aid1721',
        'aid2100',
        'aid2101',
        'aid2147',
        'aid2242',
        'aid2326',
        'aid2451',
        'aid2517',
        'aid2528',
        'aid2546',
        'aid2549',
        'aid2551',
        'aid2662',
        'aid2675',
        'aid2676',
        'aid411',
        'aid463254',
        'aid485281',
        'aid485290',
        'aid485294',
        'aid485297',
        'aid485313',
        'aid485314',
        'aid485341',
        'aid485349',
        'aid485353',
        'aid485360',
        'aid485364',
        'aid485367',
        'aid492947',
        'aid493208',
        'aid504327',
        'aid504332',
        'aid504333',
        'aid504339',
        'aid504444',
        'aid504466',
        'aid504467',
        'aid504706',
        'aid504842',
        'aid504845',
        'aid504847',
        'aid504891',
        'aid540276',
        'aid540317',
        'aid588342',
        'aid588453',
        'aid588456',
        'aid588579',
        'aid588590',
        'aid588591',
        'aid588795',
        'aid588855',
        'aid602179',
        'aid602233',
        'aid602310',
        'aid602313',
        'aid602332',
        'aid624170',
        'aid624171',
        'aid624173',
        'aid624202',
        'aid624246',
        'aid624287',
        'aid624288',
        'aid624291',
        'aid624296',
        'aid624297',
        'aid624417',
        'aid651635',
        'aid651644',
        'aid651768',
        'aid651965',
        'aid652025',
        'aid652104',
        'aid652105',
        'aid652106',
        'aid686970',
        'aid686978',
        'aid686979',
        'aid720504',
        'aid720532',
        'aid720542',
        'aid720551',
        'aid720553',
        'aid720579',
        'aid720580',
        'aid720707',
        'aid720708',
        'aid720709',
        'aid720711',
        'aid743255',
        'aid743266',
        'aid875',
        'aid881',
        'aid883',
        'aid884',
        'aid885',
        'aid887',
        'aid891',
        'aid899',
        'aid902',
        'aid903',
        'aid904',
        'aid912',
        'aid914',
        'aid915',
        'aid924',
        'aid925',
        'aid926',
        'aid927',
        'aid938',
        'aid995',
        ]


    if(data_type == 'tox21' or data_type == 'Tox21'):
        return tox21

    elif(data_type == 'dud_e' or data_type == 'DUD-E' or data_type == 'dude'):
        return dude

    elif(data_type == 'muv' or data_type == 'MUV'):
        return muv

    elif(data_type == 'pcba' or data_type == 'PCBA'):
        return pcba
    else:
        raise ValueError('data_type does not exist:' + str(data_type))




