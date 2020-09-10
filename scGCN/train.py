import os
import sys
import time
import numpy as np
import pickle as pkl
import tensorflow as tf
from utils import *
from tensorflow.python.saved_model import tag_constants
from models import GCN

sys.stdout = open("output_log.txt", "w")
#' del_all_flags(FLAGS)

# Set random seed
seed = 123
np.random.seed(seed)
tf.compat.v1.set_random_seed(seed)
tf.set_random_seed(seed)

# Settings
flags = tf.app.flags
FLAGS = flags.FLAGS
flags.DEFINE_string('dataset', 'input', 'data dir')
flags.DEFINE_string('model', 'gcn',
                    'Model string.')  # 'gcn', 'gcn_cheby', 'dense'
flags.DEFINE_float('learning_rate', 0.01, 'Initial learning rate.')
flags.DEFINE_integer('epochs', 200, 'Number of epochs to train.')
flags.DEFINE_integer('hidden1', 32, 'Number of units in hidden layer 1.')
flags.DEFINE_float('dropout', 0, 'Dropout rate (1 - keep probability).')
flags.DEFINE_float('weight_decay', 0,
                   'Weight for L2 loss on embedding matrix.')
flags.DEFINE_integer('early_stopping', 10,
                     'Tolerance for early stopping (# of epochs).')
flags.DEFINE_integer('max_degree', 3, 'Maximum Chebyshev polynomial degree.')

# Load data
adj, features, labels_binary_train, labels_binary_val, labels_binary_test, train_mask, pred_mask, val_mask, test_mask, new_label, true_label, index_guide = load_data(
    FLAGS.dataset)

support = [preprocess_adj(adj)]
num_supports = 1
model_func = GCN

# Define placeholders
placeholders = {
    'support':
    [tf.sparse_placeholder(tf.float32) for _ in range(num_supports)],
    'features':
    tf.sparse_placeholder(tf.float32,
                          shape=tf.constant(features[2], dtype=tf.int64)),
    'labels':
    tf.placeholder(tf.float32, shape=(None, labels_binary_train.shape[1])),
    'labels_mask':
    tf.placeholder(tf.int32),
    'dropout':
    tf.placeholder_with_default(0., shape=()),
    'num_features_nonzero':
    tf.placeholder(tf.int32)  # helper variable for sparse dropout
}

# Create model
model = model_func(placeholders, input_dim=features[2][1], logging=True)


# Define model evaluation function
def evaluate(features, support, labels, mask, placeholders):
    t_test = time.time()
    feed_dict_val = construct_feed_dict(features, support, labels, mask,
                                        placeholders)
    outs_val = sess.run([model.loss, model.accuracy], feed_dict=feed_dict_val)
    return outs_val[0], outs_val[1], (time.time() - t_test)


# Initialize session
sess = tf.Session()
# Init variables
sess.run(tf.global_variables_initializer())

train_accuracy = []
train_loss = []
val_accuracy = []
val_loss = []
test_accuracy = []
test_loss = []

# Train model

#configurate checkpoint directory to save intermediate model training weights
saver = tf.train.Saver()
save_dir = 'checkpoints/'
if not os.path.exists(save_dir):
    os.makedirs(save_dir)

save_path = os.path.join(save_dir, 'best_validation')

for epoch in range(FLAGS.epochs):
    t = time.time()
    # Construct feed dictionary
    feed_dict = construct_feed_dict(features, support, labels_binary_train,
                                    train_mask, placeholders)
    feed_dict.update({placeholders['dropout']: FLAGS.dropout})
    # Training step
    outs = sess.run([model.opt_op, model.loss, model.accuracy],
                    feed_dict=feed_dict)
    train_accuracy.append(outs[2])
    train_loss.append(outs[1])
    # Validation
    cost, acc, duration = evaluate(features, support, labels_binary_val,
                                   val_mask, placeholders)
    val_loss.append(cost)
    val_accuracy.append(acc)
    test_cost, test_acc, test_duration = evaluate(features, support,
                                                  labels_binary_test,
                                                  test_mask, placeholders)
    test_accuracy.append(test_acc)
    test_loss.append(test_cost)
    saver.save(sess=sess, save_path=save_path)
    print("Epoch:", '%04d' % (epoch + 1), "train_loss=",
          "{:.5f}".format(outs[1]), "train_acc=", "{:.5f}".format(outs[2]),
          "val_loss=", "{:.5f}".format(cost), "val_acc=", "{:.5f}".format(acc),
          "time=", "{:.5f}".format(time.time() - t))
    if epoch > FLAGS.early_stopping and val_loss[-1] > np.mean(
            val_loss[-(FLAGS.early_stopping + 1):-1]):
        print("Early stopping...")
        break

print("Finished Training....")

test_cost, test_acc, test_duration = evaluate(features, support,
                                              labels_binary_test, test_mask,
                                              placeholders)
print("Test set results:", "cost=", "{:.5f}".format(test_cost), "accuracy=",
      "{:.5f}".format(test_acc), "time=", "{:.5f}".format(test_duration))

#' --------------- --------------- ---------------
#'  all outputs : prediction and activation
#' --------------- --------------- ---------------

all_mask = np.array([True] * len(train_mask))
labels_binary_all = new_label

feed_dict_all = construct_feed_dict(features, support, labels_binary_all,
                                    all_mask, placeholders)
feed_dict_all.update({placeholders['dropout']: FLAGS.dropout})

activation_output = sess.run(model.activations, feed_dict=feed_dict_all)[1]
predict_output = sess.run(model.outputs, feed_dict=feed_dict_all)

#' ------- accuracy on all masks ---------
ab = sess.run(tf.nn.softmax(predict_output))
all_prediction = sess.run(
    tf.equal(sess.run(tf.argmax(ab, 1)),
             sess.run(tf.argmax(labels_binary_all, 1))))

#' ------- accuracy on prediction masks ---------
acc_train = np.sum(all_prediction[train_mask]) / np.sum(train_mask)
acc_test = np.sum(all_prediction[test_mask]) / np.sum(test_mask)
acc_val = np.sum(all_prediction[val_mask]) / np.sum(val_mask)
acc_pred = np.sum(all_prediction[pred_mask]) / np.sum(pred_mask)
print('Checking train/test/val set accuracy: {}, {}, {}'.format(
    acc_train, acc_test, acc_val))
print('Checking pred set accuracy: {}'.format(acc_pred))