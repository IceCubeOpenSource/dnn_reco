from __future__ import division, print_function
import tensorflow as tf
import numpy as np

from dnn_reco import misc
from dnn_reco import utils
from dnn_reco.modules.loss.utils import loss_utils

"""
All defined models must have the following signature:

    Parameters
    ----------
    config : dict
        Dictionary containing all settings as read in from config file.
    data_handler : :obj: of class DataHandler
        An instance of the DataHandler class. The object is used to obtain
        meta data.
    data_transformer : :obj: of class DataTransformer
        An instance of the DataTransformer class. The object is used to
        transform data.
    shared_objects : dict
        A dictionary containg settings and objects that are shared and passed
        on to sub modules.
    *args
        Variable length argument list.
    **kwargs
        Arbitrary keyword arguments.

    Returns
    -------
    tf.Tensor
        A tensorflow tensor containing the loss for each label.
        A weighted sum with weights as defined in the config will be performed
        over these loss terms to obtain a scalar loss.
        Shape: label_shape (same shape as labels)
"""


def track_pos_mse(config, data_handler, data_transformer, shared_objects,
                  *args, **kwargs):
    """The MSE of the 4-vector distance of the predicted vertex (x, y, z, t)
    and the infinite track given by the true direction.

    The label is set up such that all points on the infinite track are correct
    predictions. This loss only applies to vertex (x, y, z, t) via the labels
    'pos_x', 'pos_y', 'pos_z', 'time as defined in the label_particle_keys.

    Parameters
    ----------
    config : dict
        Dictionary containing all settings as read in from config file.
    data_handler : :obj: of class DataHandler
        An instance of the DataHandler class. The object is used to obtain
        meta data.
    data_transformer : :obj: of class DataTransformer
        An instance of the DataTransformer class. The object is used to
        transform data.
    shared_objects : dict
        A dictionary containg settings and objects that are shared and passed
        on to sub modules.
    *args
        Variable length argument list.
    **kwargs
        Arbitrary keyword arguments.

    Returns
    -------
    tf.Tensor
        A tensorflow tensor containing the loss for each label.
        Shape: label_shape (same shape as labels)

    """
    index_dir_x = data_handler.get_label_index(config['label_dir_x_key'])
    index_dir_y = data_handler.get_label_index(config['label_dir_y_key'])
    index_dir_z = data_handler.get_label_index(config['label_dir_z_key'])

    index_pos_x = data_handler.get_label_index(
        config['label_particle_keys']['pos_x'])
    index_pos_y = data_handler.get_label_index(
        config['label_particle_keys']['pos_y'])
    index_pos_z = data_handler.get_label_index(
        config['label_particle_keys']['pos_z'])
    index_time = data_handler.get_label_index(
        config['label_particle_keys']['time'])

    dir_x_true = shared_objects['y_true'][:, index_dir_x]
    dir_y_true = shared_objects['y_true'][:, index_dir_y]
    dir_z_true = shared_objects['y_true'][:, index_dir_z]

    x_true = shared_objects['y_true'][:, index_pos_x]
    y_true = shared_objects['y_true'][:, index_pos_y]
    z_true = shared_objects['y_true'][:, index_pos_z]
    time_true = shared_objects['y_true'][:, index_time]

    x_pred = shared_objects['y_pred'][:, index_pos_x]
    y_pred = shared_objects['y_pred'][:, index_pos_y]
    z_pred = shared_objects['y_pred'][:, index_pos_z]
    time_pred = shared_objects['y_pred'][:, index_time]

    x_unc = shared_objects['y_unc'][:, index_pos_x]
    y_unc = shared_objects['y_unc'][:, index_pos_y]
    z_unc = shared_objects['y_unc'][:, index_pos_z]
    time_unc = shared_objects['y_unc'][:, index_time]

    # x: predicted point, p: true point on track, d: true unit direction vector
    # calculate a = x - p
    a1 = x_pred - x_true
    a2 = y_pred - y_true
    a3 = z_pred - z_true

    # scalar product s = a*d, s is distance to closest point on infinite track
    s = a1*dir_x_true + a2*dir_y_true + a3*dir_z_true

    # caculate r = s*d -a = (p + s*d) - x
    r1 = s*dir_x_true - a1
    r2 = s*dir_y_true - a2
    r3 = s*dir_z_true - a3

    # calculate time at closest approach point on infinite track
    c = 0.299792458  # in m /ns
    rt = time_true + s / c - time_pred

    unc_diff_x = tf.stop_gradient(r1) - x_unc
    unc_diff_y = tf.stop_gradient(r2) - y_unc
    unc_diff_z = tf.stop_gradient(r3) - z_unc
    unc_diff_t = tf.stop_gradient(rt) - time_unc

    if 'event_weights' in shared_objects:
        weights = shared_objects['event_weights']
        w_sum = tf.reduce_sum(weights, axis=0)
        loss_x = tf.reduce_sum((r1**2 + unc_diff_x**2) * weights, 0) / w_sum
        loss_y = tf.reduce_sum((r2**2 + unc_diff_y**2) * weights, 0) / w_sum
        loss_z = tf.reduce_sum((r3**2 + unc_diff_z**2) * weights, 0) / w_sum
        loss_t = tf.reduce_sum((rt**2 + unc_diff_t**2) * weights, 0) / w_sum
    else:
        loss_x = tf.reduce_mean(r1**2 + unc_diff_x**2, 0)
        loss_y = tf.reduce_mean(r2**2 + unc_diff_y**2, 0)
        loss_z = tf.reduce_mean(r3**2 + unc_diff_z**2, 0)
        loss_t = tf.reduce_mean(rt**2 + unc_diff_t**2, 0)

    zeros = tf.zeros_like(loss_x)

    loss_all_list = []
    for label in data_handler.label_names:

        if label == index_pos_x:
            loss_all_list.append(loss_x)

        elif label == index_pos_y:
            loss_all_list.append(loss_y)

        elif label == index_pos_z:
            loss_all_list.append(loss_z)

        elif label == index_time:
            loss_all_list.append(loss_t)

        else:
            loss_all_list.append(zeros)

    loss_all = tf.stack(loss_all_list, axis=0)

    loss_utils.add_logging_info(data_handler, shared_objects)

    return loss_all


def track_pos_gaussian(config, data_handler, data_transformer, shared_objects,
                       *args, **kwargs):
    """The Gaussian Likelihood loss of the 4-vector distance of the predicted
    vertex (x, y, z, t) and the infinite track given by the true direction.

    The label is set up such that all points on the infinite track are correct
    predictions. This loss only applies to vertex (x, y, z, t) via the labels
    'pos_x', 'pos_y', 'pos_z', 'time' as defined in the label_particle_keys.

    Parameters
    ----------
    config : dict
        Dictionary containing all settings as read in from config file.
    data_handler : :obj: of class DataHandler
        An instance of the DataHandler class. The object is used to obtain
        meta data.
    data_transformer : :obj: of class DataTransformer
        An instance of the DataTransformer class. The object is used to
        transform data.
    shared_objects : dict
        A dictionary containg settings and objects that are shared and passed
        on to sub modules.
    *args
        Variable length argument list.
    **kwargs
        Arbitrary keyword arguments.

    Returns
    -------
    tf.Tensor
        A tensorflow tensor containing the loss for each label.
        Shape: label_shape (same shape as labels)

    """
    index_dir_x = data_handler.get_label_index(config['label_dir_x_key'])
    index_dir_y = data_handler.get_label_index(config['label_dir_y_key'])
    index_dir_z = data_handler.get_label_index(config['label_dir_z_key'])

    index_pos_x = data_handler.get_label_index(
        config['label_particle_keys']['pos_x'])
    index_pos_y = data_handler.get_label_index(
        config['label_particle_keys']['pos_y'])
    index_pos_z = data_handler.get_label_index(
        config['label_particle_keys']['pos_z'])
    index_time = data_handler.get_label_index(
        config['label_particle_keys']['time'])

    dir_x_true = shared_objects['y_true'][:, index_dir_x]
    dir_y_true = shared_objects['y_true'][:, index_dir_y]
    dir_z_true = shared_objects['y_true'][:, index_dir_z]

    x_true = shared_objects['y_true'][:, index_pos_x]
    y_true = shared_objects['y_true'][:, index_pos_y]
    z_true = shared_objects['y_true'][:, index_pos_z]
    time_true = shared_objects['y_true'][:, index_time]

    x_pred = shared_objects['y_pred'][:, index_pos_x]
    y_pred = shared_objects['y_pred'][:, index_pos_y]
    z_pred = shared_objects['y_pred'][:, index_pos_z]
    time_pred = shared_objects['y_pred'][:, index_time]

    x_unc = shared_objects['y_unc'][:, index_pos_x]
    y_unc = shared_objects['y_unc'][:, index_pos_y]
    z_unc = shared_objects['y_unc'][:, index_pos_z]
    time_unc = shared_objects['y_unc'][:, index_time]

    # x: predicted point, p: true point on track, d: true unit direction vector
    # calculate a = x - p
    a1 = x_pred - x_true
    a2 = y_pred - y_true
    a3 = z_pred - z_true

    # scalar product s = a*d, s is distance to closest point on infinite track
    s = a1*dir_x_true + a2*dir_y_true + a3*dir_z_true

    # caculate r = s*d -a = (p + s*d) - x
    r1 = s*dir_x_true - a1
    r2 = s*dir_y_true - a2
    r3 = s*dir_z_true - a3

    # calculate time at closest approach point on infinite track
    c = 0.299792458  # in m /ns
    rt = time_true + s / c - time_pred

    gl_x = 2*tf.log(x_unc) + (r1 / x_unc)**2
    gl_y = 2*tf.log(y_unc) + (r2 / y_unc)**2
    gl_z = 2*tf.log(z_unc) + (r3 / z_unc)**2
    gl_t = 2*tf.log(time_unc) + (rt / time_unc)**2

    if 'event_weights' in shared_objects:
        weights = shared_objects['event_weights']
        w_sum = tf.reduce_sum(weights, axis=0)
        loss_x = tf.reduce_sum(gl_x * weights, 0) / w_sum
        loss_y = tf.reduce_sum(gl_y * weights, 0) / w_sum
        loss_z = tf.reduce_sum(gl_z * weights, 0) / w_sum
        loss_t = tf.reduce_sum(gl_t * weights, 0) / w_sum
    else:
        loss_x = tf.reduce_mean(gl_x, 0)
        loss_y = tf.reduce_mean(gl_y, 0)
        loss_z = tf.reduce_mean(gl_z, 0)
        loss_t = tf.reduce_mean(gl_t, 0)

    zeros = tf.zeros_like(loss_x)

    loss_all_list = []
    for label in data_handler.label_names:

        if label == index_pos_x:
            loss_all_list.append(loss_x)

        elif label == index_pos_y:
            loss_all_list.append(loss_y)

        elif label == index_pos_z:
            loss_all_list.append(loss_z)

        elif label == index_time:
            loss_all_list.append(loss_t)

        else:
            loss_all_list.append(zeros)

    loss_all = tf.stack(loss_all_list, axis=0)

    loss_utils.add_logging_info(data_handler, shared_objects)

    return loss_all
