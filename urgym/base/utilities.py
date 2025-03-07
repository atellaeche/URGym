import pybullet as p
import glob
from collections import namedtuple
import functools
import torch
import cv2
from scipy import ndimage
import numpy as np
import math


class Models:
    def load_objects(self):
        raise NotImplementedError

    def __len__(self):
        raise NotImplementedError

    def __getitem__(self, item):
        return NotImplementedError


class YCBModels(Models):
    def __init__(self, root, selected_names: tuple = ()):
        self.obj_files = glob.glob(root)
        self.selected_names = selected_names

        self.visual_shapes = []
        self.collision_shapes = []

    def load_objects(self):
        shift = [0, 0, 0]
        mesh_scale = [1, 1, 1]

        for filename in self.obj_files:
            # Check selected_names
            if self.selected_names:
                in_selected = False
                for name in self.selected_names:
                    if name in filename:
                        in_selected = True
                if not in_selected:
                    continue
            print('Loading %s' % filename)
            self.collision_shapes.append(
                p.createCollisionShape(shapeType=p.GEOM_MESH,
                                       fileName=filename,
                                       collisionFramePosition=shift,
                                       meshScale=mesh_scale))
            self.visual_shapes.append(
                p.createVisualShape(shapeType=p.GEOM_MESH,
                                    fileName=filename,
                                    visualFramePosition=shift,
                                    meshScale=mesh_scale))

    def __len__(self):
        return len(self.collision_shapes)

    def __getitem__(self, idx):
        return self.visual_shapes[idx], self.collision_shapes[idx]


class Camera:
    def __init__(self, cam_pos, cam_tar, cam_up_vector, near, far, size, fov):
        self.width, self.height = size
        self.near, self.far = near, far
        self.fov = fov

        aspect = self.width / self.height
        self.view_matrix = p.computeViewMatrix(cam_pos, cam_tar, cam_up_vector)
        self.projection_matrix = p.computeProjectionMatrixFOV(self.fov, aspect, self.near, self.far)

        _view_matrix = np.array(self.view_matrix).reshape((4, 4), order='F')
        _projection_matrix = np.array(self.projection_matrix).reshape((4, 4), order='F')
        self.tran_pix_world = np.linalg.inv(_projection_matrix @ _view_matrix)

    def rgbd_2_world(self, w, h, d):
        x = (2 * w - self.width) / self.width
        y = -(2 * h - self.height) / self.height
        z = 2 * d - 1
        pix_pos = np.array((x, y, z, 1))
        position = self.tran_pix_world @ pix_pos
        position /= position[3]

        return position[:3]

    def shot(self):
        # Get depth values using the OpenGL renderer
        _w, _h, rgb, depth, seg = p.getCameraImage(self.width, self.height,
                                                   self.view_matrix, self.projection_matrix,
                                                   )
        return rgb, depth, seg

    def rgbd_2_world_batch(self, depth):
        # reference: https://stackoverflow.com/a/62247245
        x = (2 * np.arange(0, self.width) - self.width) / self.width
        x = np.repeat(x[None, :], self.height, axis=0)
        y = -(2 * np.arange(0, self.height) - self.height) / self.height
        y = np.repeat(y[:, None], self.width, axis=1)
        z = 2 * depth - 1

        pix_pos = np.array([x.flatten(), y.flatten(), z.flatten(), np.ones_like(z.flatten())]).T
        position = self.tran_pix_world @ pix_pos.T
        position = position.T
        # print(position)

        position[:, :] /= position[:, 3:4]

        return position[:, :3].reshape(*x.shape, -1)

def print_links(body_id):
    """
    Prints the number of links (parts) in the body and information about each joint/link.

    Parameters:
    - body_id: The ID of the body

    Returns:
    None
    """
    num_joints = p.getNumJoints(body_id)
    print("Number of links (parts) in the body:", num_joints)

    # Print base link information (base link has index -1)
    base_link_name = p.getBodyInfo(body_id)[0].decode('utf-8')
    print(f"Link ID -1: {base_link_name}")

    # Print information about each joint/link
    for i in range(num_joints):
        joint_info = p.getJointInfo(body_id, i)
        link_name = joint_info[12].decode('utf-8')
        print(f"Link ID {i}: {link_name}")

def rotate_quaternion(quaternion, angle, axis):
    """
    Rotates a quaternion by a given angle around a given axis.

    Parameters:
    - quaternion: The quaternion to rotate
    - angle: The angle to rotate
    - axis: The axis to rotate around

    Returns:
    The rotated quaternion
    """
    # Create a quaternion from the axis and angle
    rot_quaternion = p.getQuaternionFromAxisAngle(axis, angle)
    # Multiply the original quaternion by the rotation quaternion
    return quaternion_multiply(quaternion, rot_quaternion)

def quaternion_multiply(quat1, quat2):
    """
    Multiplies two quaternions.

    Parameters:
    - quat1: The first quaternion
    - quat2: The second quaternion

    Returns:
    The result of the multiplication
    """

    # Get the real and imaginary parts of the quaternions
    x1, y1, z1, w1 = quat1
    x2, y2, z2, w2 = quat2

    # Calculate the real part of the result
    w = w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2
    # Calculate the imaginary parts of the result
    x = w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2
    y = w1 * y2 + y1 * w2 + z1 * x2 - x1 * z2
    z = w1 * z2 + z1 * w2 + x1 * y2 - y1 * x2

    return x, y, z, w
    
def normalize_quaternion(qx, qy, qz, qw):
    # Calculate the norm of the quaternion
    norm = np.sqrt(qx**2 + qy**2 + qz**2 + qw**2)
    
    # If the norm is 0, we cannot normalize the quaternion, return a default valid quaternion
    if norm == 0:
        return 0.0, 0.0, 0.0, 1.0
    
    # Normalize the quaternion
    qx /= norm
    qy /= norm
    qz /= norm
    qw /= norm
    
    return qx, qy, qz, qw

def geometric_distance_reward(value: float, threshold_sign: float, threshold_max: float) -> float:
    """Returns a geometric reward which is positive from 0 to +1 in the range [0, threshold_sign] and negative for values larger than
    threshold_sign, approaching -1 in threshold_max  

    Args:
        value (type): distance value between 0 and infinity.A value of 0 is a reward of +1
        threshold_sign (type): threshold that divides positive and negative rewards
        threshold_max (type): maximum value of distance to generate a -1 reward

    Returns:
        float: a normalized reward between -1 and +1
    """
    value = max (value, 1e-10) # To avoid division by zero
    factor1 = (value - threshold_sign) / value
    factor2 = max(threshold_max - value, 1e-10)  # To avoid division by zero
    return -np.tanh(factor1/factor2)

def print_link_names_and_indices(id):
    """
    Prints the link names and indices of an object.

    :param id: The ID of the object in the PyBullet simulation
    """
    num_joints = p.getNumJoints(id)
    print(f"Object ID: {id} has {num_joints} joints/links.")

    for i in range(num_joints):
        link_info = p.getJointInfo(id, i)
        link_name = link_info[12].decode('utf-8')  # Link name is at index 12
        print(f"Link Index: {i}, Link Name: {link_name}")


def is_pointing_downwards(qx, qy, qz, qw, threshold=1e-1):    
    return z_alignment_distance(qx, qy, qz, qw) <= threshold


def _z_alignment_distance(qx, qy, qz, qw):
    # If aligned in z direction downwards:
    # qx = -qz and qy = qw

    # These differences should be close to zero if the object is vertically downwards
    diff1 = abs(qx + qz) 
    diff2 = abs(qy - qw) 

    scaled_difference = (diff1 + diff2) / 4 # Always in the range from 0 to 1

    #print(f"qx: {qx}, qy: {qy}, qz: {qz}, qw: {qw}")
    
    # Return the scaled difference
    return scaled_difference

def z_alignment_distance(roll, pitch, yaw):
    
    # The ideal downward direction vector
    downward = np.array([0, 0, -1])
    
    # Calculate the rotation matrix from Euler angles
    Rx = np.array([
        [1, 0, 0],
        [0, np.cos(roll), -np.sin(roll)],
        [0, np.sin(roll), np.cos(roll)]
    ])
    
    Ry = np.array([
        [np.cos(pitch), 0, np.sin(pitch)],
        [0, 1, 0],
        [-np.sin(pitch), 0, np.cos(pitch)]
    ])
    
    Rz = np.array([
        [np.cos(yaw), -np.sin(yaw), 0],
        [np.sin(yaw), np.cos(yaw), 0],
        [0, 0, 1]
    ])
    
    # Combined rotation matrix
    R = Rz @ Ry @ Rx
    
    # Rotate the downward direction vector
    rotated_downward = R @ downward
    
    # Compute the cosine of the angle between the vectors
    dot_product = np.dot(rotated_downward, downward)
    magnitude_rotated_downward = np.linalg.norm(rotated_downward)
    magnitude_downward = np.linalg.norm(downward)
    
    cos_theta = dot_product / (magnitude_rotated_downward * magnitude_downward)
    
    # Compute the angle in radians
    theta = np.arccos(np.clip(cos_theta, -1.0, 1.0))
    
    # Normalize the angle to the range [0, 1]
    normalized_theta = theta / np.pi
    
    return normalized_theta