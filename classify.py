#/home/ngetty/dev/anaconda2/bin/python
import warnings
import pandas as pd
import numpy as np
from time import time
import logging
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.metrics import accuracy_score
warnings.filterwarnings("ignore", category=DeprecationWarning)
from xgboost import XGBClassifier
from scipy.sparse import csr_matrix, hstack
import sys
from sklearn.decomposition import TruncatedSVD
from memory_profiler import memory_usage
from lightgbm import LGBMClassifier
import plot_cm as pcm
import argparse


def cross_validation_accuracy(clf, X, labels, skf, m):
    """ 
    Compute the average testing accuracy over k folds of cross-validation. 
    Params:
        clf......A classifier.
        X........A matrix of features.
        labels...The true labels for each instance in X
        split........The fold indices
        m............The model name
    Returns:
        The average testing accuracy of the classifier
        over each fold of cross-validation.
    """
    scores = []
    train_scores = []
    t5s = []
    for train_index, test_index in skf:
        X_train, X_test = X[train_index], X[test_index]
        y_train, y_test = labels[train_index], labels[test_index]
        if m == 'RandomForest':
            clf.fit(X_train, y_train)
        else:
            clf.fit(X_train, y_train,
                    eval_set=[(X_train, y_train), (X_test, y_test)],
                    early_stopping_rounds=2,
                    verbose=False,)
        t5, score = top_5_accuracy(clf.predict_proba(X_test), y_test)
        train_pred = clf.predict(X_train)
        train_score = accuracy_score(y_train, train_pred)
        scores.append(score)
        t5s.append(t5)
        train_scores.append(train_score)

    return np.mean(scores), np.mean(train_scores), np.mean(t5s)


def test_train_split(clf, split, m, class_names):
    """
    Compute the accuracy of a train/test split
    Params:
        clf......A classifier.
        split....indices
    Returns:
        The testing accuracy and the confusion
        matrix.
    """

    X_train, X_test, y_train, y_test = split
    if m == 'RandomForest':
        clf.fit(X_train, y_train)
    else:
        clf.fit(X_train, y_train,
                eval_set=[(X_train, y_train), (X_test, y_test)],
                early_stopping_rounds=2,
                verbose=False,)
    probs = clf.predict_proba(X_test)
    t5, score = top_5_accuracy(probs, y_test)
    train_pred = clf.predict(X_train)
    train_score = accuracy_score(y_train, train_pred)

    test_pred = clf.predict(X_test)

    stats_df = pcm.class_statistics(y_test, test_pred, class_names)
    stats_df.to_csv('results/stats/' + m + '.csv', index=0, columns=["PGF", 'Sensitivity', 'Specicifity',
                             'Most FN', 'Most FP'])
    stats_df.sort_values(by='Sensitivity', ascending=True, inplace=True, )

    #pcm.pcm(y_test, test_pred, m)

    print "Top 5 accuracy:", t5
    logging.info("Top 5 accuracy: %f", t5)

    return score, train_score, clf, t5


def classify_all(class_names, features, clfs, folds, model_names, cv, mem):
    """ 
    Compute the average testing accuracy over k folds of cross-validation. 
    Params:
        labels.......The true labels for each instance in X
        features.....The feature vectors for each instance
        clfs.........The classifiers to fit and test
        folds........Number of folds for cross validation
        model_names..Readable names of each classifier
        cv...........Whether to use cross validation
        mem..........Whether to store memory usage
    """
    labels = convert_labels(class_names)
    class_names = unique_class_names(class_names)

    tts_split = train_test_split(
        features, labels, test_size=0.2, random_state=0, stratify=labels)
    if cv:
        skf = list(StratifiedKFold(n_splits=folds, shuffle=True).split(features, labels))

    results = pd.DataFrame(columns=["Model", "CV Train Acc", "CV Val Acc", "CV T5 Acc", "Split Train Acc", "Split Val Acc", "Top 5 Val Acc", "Max Mem", "Avg Mem", "Time"])

    for x in range(len(model_names)):
        start = time()
        mn = model_names[x]

        print "Classiying with", mn
        logging.info("Classifying with %s", mn)

        clf = clfs[x]

        if cv:
            cv_score, cv_train_score, cv_t5 = cross_validation_accuracy(clf, features, labels, skf, mn)
            print "%s %d fold cross validation mean train accuracy: %f" % (mn, folds, cv_train_score)
            logging.info("%s %d fold cross validation mean train accuracy: %f" % (mn, folds, cv_train_score))
            print "%s %d fold cross validation mean top 5 accuracy: %f" % (mn, folds, cv_t5)
            logging.info("%s %d fold cross validation mean top 5 accuracy: %f" % (mn, folds, cv_t5))
            print "%s %d fold cross validation mean validation accuracy: %f" % (mn, folds, cv_score)
            logging.info("%s %d fold cross validation mean validation accuracy: %f" % (mn, folds, cv_score))
        else:
            cv_score = -1
            cv_train_score = -1
            cv_t5 = -1

        args = (clf, tts_split, mn, class_names)
        if mem:
            mem_usage, retval = memory_usage((test_train_split, args), interval=1.0, retval=True)
            tts_score, tts_train_score, clf, t5 = retval

            avg_mem = np.mean(mem_usage)
            max_mem = max(mem_usage)
            print('Average memory usage: %s' % avg_mem)
            print('Maximum memory usage: %s' % max_mem)
            # np.savetxt("results/mem-usage/mem." + args[0], mem_usage, delimiter=',')
        else:
            tts_score, tts_train_score, clf, t5 = test_train_split(*args)
            avg_mem = -1
            max_mem = -1

        feat_score = clf.feature_importances_
        sorted_feats = np.argsort(feat_score)[::-1]
        np.savetxt('results/' + mn + '.sorted_features', np.vstack((sorted_feats,feat_score[sorted_feats])))
        top_10_features = sorted_feats[:10]

        print "Top ten feature idxs", top_10_features
        logging.info("Top ten feature idxs: %s", str(top_10_features))

        print "Training accuracy:", tts_train_score
        print "Validation accuracy:", tts_score
        logging.info("Training accuracy: %f", tts_train_score)
        logging.info("test/train split accuracy: %f", tts_score)
        end = time()
        elapsed = end-start
        print "Time elapsed for model %s is %f" % (mn, elapsed)
        logging.info("Time elapsed for model %s is %f" % (mn, elapsed))
        results.loc[results.shape[0]] = ([mn, cv_train_score, cv_score, cv_t5, tts_train_score, tts_score, t5, max_mem, avg_mem, elapsed])
        
    return results


def unique_class_names(names):
    """ 
    Generate ordered unique class names
    Params:
        names....Label for every data point
    Returns:
        Name for each class in the set
    """
    cns = set()
    unique = []
    for c in names:
        if c not in cns:
            unique.append(c)
            cns.add(c)

    return unique


def top_5_accuracy(probs, y_true):
    """ 
    Calculates top 5 and top 1 accuracy in 1 go
    Params:
        probs.....NxC matrix, class probabilities for each class
        y_true....True class labels
    Returns:
        top5 accuracy
        top1 accuracy
    """
    top5 = np.argsort(probs, axis=1)[:,-5:]
    c = 0
    top1c = 0
    for x in range(len(top5)):
        if np.in1d(y_true[x], top5[x], assume_unique=True)[0]:
            c += 1
        if y_true[x] == top5[x][4]:
            top1c += 1

    return float(c)/len(y_true), float(top1c)/len(y_true)


def convert_labels(labels):
    """ 
    Convert labels to indexes
    Params:
        labels...Original k class string labels
    Returns:
        Categorical label vector
    """
    label_idxs = {}
    new_labels = np.empty(len(labels))
    for x in range(len(labels)):
        new_labels[x] = label_idxs.setdefault(labels[x], len(label_idxs))
    return new_labels


def load_sparse_csr(filename):
    loader = np.load(filename)
    return csr_matrix((loader['data'], loader['indices'], loader['indptr']),
                         shape=loader['shape'], dtype="float32"), loader['labels']


def load_data(size, file2, file3):
    path = "data/" + size + '/'

    if file2 and file3:
        print "Using 1, 3, 5 and 10mers"
        features, labels = load_sparse_csr(path + "feature_matrix.3.5.10.csr.npz")
        #features = hstack((features[:,:37], features[:,8458:]), format='csr')
    else:
        features, labels = load_sparse_csr(path + "feature_matrix.3.csr.npz")
        print "AA 1mers 2mers 3mers"
        # features = features[:,32:]
        # features = hstack((features[:,32:432], features[:,-22:]), format='csr')
        # features = hstack((features[:,:432], features[:,-22:]), format='csr')
        features = features[:,-22:]
        #features = features[:,:37]
        if file2:
            print "Adding 5mer count features"
            features2, _ = load_sparse_csr(path + "feature_matrix.5.csr.npz")
            features2 = features2[:, :-5]
            features = hstack([features, features2], format='csr')

    return features, labels


def get_parser():
    parser = argparse.ArgumentParser(description='Classify protein function with ensemble methods')
    parser.add_argument("--data", default='sm', type=str, help="data to use")
    parser.add_argument("--five", default=False, action='store_true', help="add 5mer features")
    parser.add_argument("--ten", default=False, action='store_true', help="add 10mer features")
    parser.add_argument("--redu", default=0, type=int, help="feature reduction with Truncated SVD")
    parser.add_argument("--tfidf", default=False, help="convert counts to tfidf")
    parser.add_argument("--prune", default=0, type=int, help="remove features with apperance below prune")
    parser.add_argument("--est", default=16, type=int, help="number of estimators (trees)")
    parser.add_argument("--thresh", default=0, type=int, help="zero counts below threshold")
    parser.add_argument("--cv", default=False, action='store_true', help="calculate cross validation results")
    parser.add_argument("--mem", default=False, action='store_true', help="store memory usage statistics")
    parser.add_argument("--truncate", default=0, type=int, help="Use only top k ")

    return parser


def main():
    parser = get_parser()
    args = parser.parse_args()
    est = args.est
    thresh = args.thresh
    prune = args.prune

    folds = 5

    clfs = [RandomForestClassifier(n_jobs=-1
                                   ,n_estimators=int(est)
                                   #,oob_score=True
                                   ,max_depth=8
                                   ),

           XGBClassifier(n_jobs=-1,
                          n_estimators=int(est)
                          ,objective="multi:softprob"
                          ,max_depth=2
                          ,learning_rate=1
                          ,colsample_bytree=0.8
                          ,subsample=0.8
                          ,min_child_weight=6
                         ),

            LGBMClassifier(nthread=-1
                           ,num_leaves=3
                           ,learning_rate=1
                           ,n_estimators=int(est)
                           ,colsample_bytree=0.8
                           ,subsample=0.8
                           ,min_child_weight=6
                           )
            ]

    model_names = ["RandomForest"
                   ,"XGBoost"
                   ,"LightGBM"
             ]

    features, class_names = load_data(args.data, args.five, args.ten)

    # Zero-out counts below the given threshold
    if thresh > 0:
        v = np.sum(features.data <= thresh)
        print "Values less than threshhold,", v
        logging.info("Values less than threshhold,", v)
        features.data *= features.data > thresh

    # Remove feature columns that have sample below threshhold
    nonzero_counts = features.getnnz(0)
    nonz = nonzero_counts > int(prune)

    print "Removing %d features that do not have more than %s nonzero counts" % (
    features.shape[1] - np.sum(nonz), prune)
    logging.info(
        "Removing %d features that do not have more than %s nonzero counts" % (features.shape[1] - np.sum(nonz), prune))

    features = features[:, nonz]

    if args.tfidf:
        print "Converting features to tfidf"
        logging.info("Converting features to tfidf")
        tfer = TfidfTransformer()
        tfer.fit(features[:,:32],class_names)
        features_tf = tfer.transform(features[:,:32])
        features = hstack([features_tf, features[:,32:]], format='csr')
        #tfer.fit(features)
        #features = tfer.transform(features)
        features = features.astype('float32')

    # Reduce feature dimensionality
    if args.redu > 0:
        print "Starting dimensionality reduction via TruncatedSVD"
        logging.info("Starting dimensionality reduction via TruncatedSVD")
        start = time()
        svd = TruncatedSVD(n_components=int(args.redu), n_iter=5, random_state=42)
        svd.fit(features)
        features = svd.transform(features)
        end = time()
        elapsed = end - start
        print "Time elapsed for dimensionality reduction is %f" % elapsed
        logging.info("Time elapsed for dimensionality reduction is %f" % elapsed)

    if args.truncate > 0:
        fimp = np.genfromtxt("results/LightGBM.sorted_features")
        idxs = fimp[0][:args.truncate]
        features = features[:,idxs]

    print "Final data shape:", features.shape


    logging.info("Final data shape: %s" % (features.shape,))
    results = classify_all(class_names, features, clfs, folds, model_names, args.cv, args.mem)
    #results.to_csv("results/" + size + '.' + file2 + '.' + file3 + '.' + red + '.' + tfidf + '.' + prune + '.' + est, sep="\t")
    print results.to_string()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, filename="results/results.log", filemode="a+",
                        format="%(asctime)-15s %(levelname)-8s %(message)s")
        #if len(sys.argv) > 1:
        #os.chdir("/home/ngetty/examples/protein-pred")
    main()
