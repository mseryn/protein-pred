import warnings
import pandas as pd
import numpy as np
from time import time, gmtime, strftime
import logging
from scipy.sparse import csr_matrix, hstack, vstack
import argparse
from collections import Counter, defaultdict
import keras
from keras.utils import to_categorical
from keras.models import Sequential, Model
from keras.layers import Dense, Dropout, Activation, Input, merge
from keras.callbacks import ReduceLROnPlateau, CSVLogger, EarlyStopping
from sklearn.model_selection import train_test_split


def load_sparse_csr(filename):
    loader = np.load(filename)
    return csr_matrix((loader['data'], loader['indices'], loader['indptr']),
                         shape=loader['shape'], dtype="int32")


def read_cafa():
    file = "data/cafa_df"
    data = pd.read_csv(file, header=0)
    labels = load_sparse_csr("data/cafa_labels.npz")

    return to_categorical(data), labels


def read_core():
    file = "data/coreseed.train.tsv"
    core_df = pd.read_csv(file, names=["label", "dna", "aa"], usecols=[1, 5, 6], delimiter='\t', header=0)
    data = core_df.aa
    labels = core_df.label

    return to_categorical(data), to_categorical(labels)


def build_attention_model(input_dim, nb_classes):
    inputs = Input(shape=(input_dim[0],))

    # ATTENTION PART STARTS HERE
    attention_probs = Dense(input_dim[0], activation='softmax', name='attention_vec')(inputs)
    attention_mul = merge([inputs, attention_probs], output_shape=nb_classes, name='attention_mul', mode='mul')
    # ATTENTION PART FINISHES HERE

    attention_mul = Dense(64)(attention_mul)
    output = Dense(units=nb_classes, activation='sigmoid')(attention_mul)
    model = Model(input=[inputs], output=output)

    return model


def main():
    lr_reducer = ReduceLROnPlateau(factor=np.sqrt(0.1), cooldown=0, patience=5, min_lr=0.5e-6)
    early_stopper = EarlyStopping(min_delta=0.001, patience=10)
    csv_logger = CSVLogger("results/multi_task.csv")

    data, labels = read_core()

    X_train, X_test, y_train, y_test = train_test_split(
        data, labels, test_size=0.2, random_state=0, stratify=labels)

    nb_classes = 1000
    input_shape = (data.shape[1], 1)
    model = build_attention_model(input_shape, nb_classes)

    batch_size = 80
    epochs = 20

    model.fit(X_train, y_train,
              batch_size=batch_size,
              epochs=epochs,
              validation_data=(X_test, y_test), callbacks=[lr_reducer, early_stopper, csv_logger])


if __name__ == '__main__':
    main()