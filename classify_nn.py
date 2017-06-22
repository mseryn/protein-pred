from keras.models import Sequential
from keras.layers import Dense, Dropout, Activation
from keras.layers import LSTM
from keras.layers import Conv1D, MaxPooling1D
from keras.callbacks import ReduceLROnPlateau, CSVLogger, EarlyStopping
from scipy.sparse import csr_matrix, hstack
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import normalize
from keras.utils import np_utils
import sys, os
import resnet
import threading


def nn_batch_generator(X_data, y_data, batch_size, csr_2d, m):
    samples_per_epoch = X_data.shape[0]
    number_of_batches = samples_per_epoch/batch_size
    counter=0
    index = np.arange(np.shape(y_data)[0])
    while 1:
        index_batch = index[batch_size*counter:batch_size*(counter+1)]
        if not csr_2d:
            X_batch = X_data[index_batch,:].toarray()
        y_batch = y_data[index_batch]
        if m == "lstm":
            X_batch = X_batch.reshape(X_batch.shape[0],X_batch.shape[1], 1)
        else:
            X_batch = X_batch.reshape(X_batch.shape[0], X_batch.shape[1], 1, 1)
        counter += 1
        yield np.array(X_batch),y_batch
        if (counter > number_of_batches):
            counter=0


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


def build_lstm_model(nb_classes, input_shape):
    # Convolution
    kernel_size = 7
    filters = 64
    pool_size = 4

    # LSTM
    lstm_output_size = 128
    model = Sequential()
    # model.add(Dropout(0.25, input_shape=(features.shape[1:])))
    model.add(Conv1D(filters,
                     kernel_size,
                     padding='same',
                     activation='relu',
                     strides=2, input_shape=(input_shape)))
    model.add(MaxPooling1D(pool_size=pool_size))
    model.add(LSTM(lstm_output_size))
    model.add(Dense(units=nb_classes, kernel_initializer="he_normal"))
    model.add(Activation('softmax'))

    return model


def classify(features, labels, use_batches, file, m):
    lr_reducer = ReduceLROnPlateau(factor=np.sqrt(0.1), cooldown=0, patience=5, min_lr=0.5e-6)
    early_stopper = EarlyStopping(min_delta=0.001, patience=10)
    csv_logger = CSVLogger("results/" + file + '.lstm.log.csv')

    if len(labels) > 100000:
        nb_classes = 1000
    else:
        nb_classes = 100

    # Training
    batch_size = 1000
    epochs = 600

    X_train, X_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, random_state=0, stratify=labels)

    # The data, shuffled and split between train and test sets:
    Y_train = np_utils.to_categorical(y_train, nb_classes)
    Y_test = np_utils.to_categorical(y_test, nb_classes)

    rows =  1

    input_shape = (features.shape[1], rows)

    vsteps = X_test.shape[0] // batch_size if X_test.shape[0] > batch_size else 1

    if m == "lstm":
        print 'Building LSTM model...'
        model = build_lstm_model(nb_classes, input_shape)
    else:
        print 'Building RES model...'
        model = resnet.ResnetBuilder.build_resnet_101((1, features.shape[1], 1), nb_classes)

    model.compile(loss='categorical_crossentropy',
                  optimizer='adam',
                  metrics=['accuracy', 'top_k_categorical_accuracy'])

    if not use_batches:
        print('Not using batches.')
        model.fit(X_train, Y_train,
                  batch_size=batch_size,
                  epochs=epochs,
                  validation_data=(X_test, Y_test), callbacks=[lr_reducer, early_stopper, csv_logger])
    else:
        print('Using batches.')
        # Fit the model on the batches generated by datagen.flow().
        model.fit_generator(nn_batch_generator(X_train, Y_train, batch_size, False, m),
                            steps_per_epoch=X_train.shape[0] // batch_size,
                            validation_steps= vsteps,
                            validation_data=nn_batch_generator(X_test, Y_test, batch_size, False, m),
                            #workers=2,
                            epochs=epochs, verbose=1, max_q_size=100,
                            callbacks=[lr_reducer, early_stopper, csv_logger])


def load_sparse_csr(filename):
    loader = np.load(filename)
    return csr_matrix((loader['data'], loader['indices'], loader['indptr']),
                         shape=loader['shape']), loader['labels']


def load_sparse_csr_2d(filename):
    loader = np.load(filename)
    return loader['data'], loader['labels']


def load_data(size, file2, file3):
    path = "data/" + size + '/'

    if file2 and file3:
        print "Using 1, 3, 5 and 10mers"
        features, labels = load_sparse_csr(path + "feature_matrix.3.5.10.csr.npz")
        #features = hstack((features[:,:37], features[:,8458:]), format='csr')
    else:
        features, labels = load_sparse_csr(path + "feature_matrix.3.csr.npz")
        print "AA 1mers 2mers 3mers"
        features = hstack((features[:,:432], features[:,-22:]), format='csr')
        # features = hstack((features[:,32:432], features[:,-22:]), format='csr')
        #features = features[:,:37]
        if file2:
            print "Adding 5mer count features"
            features2, _ = load_sparse_csr(path + "feature_matrix.5.csr.npz")
            features2 = features2[:, :-5]
            features = hstack([features, features2], format='csr')

    return features, labels


def main(data="sm", use_batches='0', m="lstm"):
    use_batches = int(use_batches)
    use_batches = use_batches > 0

    features, labels = load_data(data, False, False)

    labels = convert_labels(labels)
    print features.shape

    features = features.toarray()
    #normalize(features, copy=False)
    features = features.reshape(features.shape[0],features.shape[1], 1)

    classify(features, labels, use_batches, data, m)


if __name__ == '__main__':
    lock = threading.Lock()
    if len(sys.argv) > 1:
        os.chdir("/home/ngetty/proj/protein-pred")
        args = sys.argv[1:]
        main(args[0], args[1], args[2])
    else:
        main()