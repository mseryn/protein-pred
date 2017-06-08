#/home/ngetty/dev/anaconda2/bin/python
"""
Adapted from keras example cifar10_cnn.py
Train ResNet-18 on the CIFAR10 small images dataset.
GPU run command with Theano backend (with TensorFlow, the GPU is automatically used):
    THEANO_FLAGS=mode=FAST_RUN,device=gpu,floatX=float32 python cifar10.py
"""

# adapted from https://github.com/raghakot/keras-resnet/blob/master/cifar10.py
from keras.utils import np_utils
from keras.callbacks import ReduceLROnPlateau, CSVLogger, EarlyStopping
from scipy.sparse import csr_matrix, hstack
import numpy as np
import resnet
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import normalize
import os
import sys


def nn_batch_generator(X_data, y_data, batch_size):
    samples_per_epoch = X_data.shape[0]
    number_of_batches = samples_per_epoch/batch_size
    counter=0
    index = np.arange(np.shape(y_data)[0])
    while 1:
        index_batch = index[batch_size*counter:batch_size*(counter+1)]
        X_batch = X_data[index_batch,:].todense()
        y_batch = y_data[index_batch]
        counter += 1
        yield np.array(X_batch),y_batch
        if (counter > number_of_batches):
            counter=0


def load_sparse_csr(filename):
    loader = np.load(filename)
    return csr_matrix((loader['data'], loader['indices'], loader['indptr']),
                         shape = loader['shape']), loader['labels']


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


def classify(features, labels, shape, use_batches):
    batch_size = 10000
    nb_epoch = 20
    nb_classes = 1000

    lr_reducer = ReduceLROnPlateau(factor=np.sqrt(0.1), cooldown=0, patience=5, min_lr=0.5e-6)
    early_stopper = EarlyStopping(min_delta=0.001, patience=10)
    csv_logger = CSVLogger("results/" + file + '.res.log.csv')

    X_train, X_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, random_state=0, stratify=labels)

    # The data, shuffled and split between train and test sets:
    Y_train = np_utils.to_categorical(y_train, nb_classes)
    Y_test = np_utils.to_categorical(y_test, nb_classes)

    model = resnet.ResnetBuilder.build_resnet_18(shape, nb_classes)
    model.compile(loss='categorical_crossentropy',
                  optimizer='adam',
                  metrics=['accuracy', 'top_k_categorical_accuracy'])

    if not use_batches:
        print('Not using sparse matrix.')
        model.fit(X_train, Y_train,
                  batch_size=batch_size,
                  epochs=nb_epoch,
                  validation_data=(X_test, Y_test),
                  shuffle=True,
                  callbacks=[lr_reducer, early_stopper, csv_logger])
    else:
        print('Using sparse matrix.')

        # Fit the model on the batches generated by datagen.flow().
        model.fit_generator(nn_batch_generator(X_train, Y_train, batch_size),
                            steps_per_epoch=X_train.shape[0] // batch_size,
                            validation_data=(X_test, Y_test),
                            epochs=nb_epoch, verbose=1, max_q_size=100,
                            callbacks=[lr_reducer, early_stopper, csv_logger])


def main(file="feature_matrix.sm.3.csr_2d.npy", file2="False"):
    use_batches = False

    features, labels = load_sparse_csr("data/" + file)
    labels = convert_labels(labels)

    if file2 != "False":
        features2, _ = load_sparse_csr("data/" + file2)
        features = hstack([features, features2])

    # input image dimensions
    img_rows, img_cols = features.shape[1], features.shape[2]
    img_channels = 1

    if not use_batches:
        features = features.toarray()
        normalize(features, copy=False)
        features = features.reshape(features.shape[0],img_rows, img_cols, img_channels)

    shape = (img_channels, img_rows, img_cols)
    classify(features, labels, shape, use_batches)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        os.chdir("/home/ngetty/examples/protein-pred")
        args = sys.argv[1:]
        main(args[0], args[1])
    else:
        main()
