# coding: utf-8
import os
import time
import cv2
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as plp


def logger(msg):
    """
        log message
    """
    now = time.ctime()
    print("[%s] %s" % (now, msg))


def createDir(p):
    if not os.path.exists(p):
        os.mkdir(p)

# shuffle in the same way


def shuffle_in_unison_scary(a, b):
    rng_state = np.random.get_state()
    np.random.shuffle(a)
    np.random.set_state(rng_state)
    np.random.shuffle(b)


def getDataFromTxt(txt, with_landmark=True):
    """
        Generate data from txt file
        return [(img_path, bbox, landmark)]
            bbox: [left, right, top, bottom]
            landmark: [(x1, y1), (x2, y2), ...]
    """
    # get dirname
    dirname = os.path.dirname(txt)
    with open(txt, 'r') as fd:
        lines = fd.readlines()

    result = []
    for line in lines:
        line = line.strip()
        components = line.split(' ')
        img_path = os.path.join(dirname, components[0])  # file path
        # bounding box, (x1, y1, x2, y2)
        #bbox = (components[1], components[2], components[3], components[4])
        bbox = (components[1], components[3], components[2], components[4])
        bbox = [float(_) for _ in bbox]
        bbox = map(int, bbox)
        # landmark
        if not with_landmark:
            result.append((img_path, BBox(bbox)))
            continue
        landmark = np.zeros((5, 2))
        for index in range(0, 5):
            rv = (float(components[5 + 2 * index]),
                  float(components[5 + 2 * index + 1]))
            landmark[index] = rv
        # normalize
        '''
        for index, one in enumerate(landmark):
            rv = ((one[0]-bbox[0])/(bbox[2]-bbox[0]), (one[1]-bbox[1])/(bbox[3]-bbox[1]))
            landmark[index] = rv
        '''
        result.append((img_path, BBox(bbox), landmark))
    return result


def getPatch(img, bbox, point, padding):
    """
        Get a patch iamge around the given point in bbox with padding
        point: relative_point in [0, 1] in bbox
    """
    point_x = bbox.x + point[0] * bbox.w
    point_y = bbox.y + point[1] * bbox.h
    patch_left = point_x - bbox.w * padding
    patch_right = point_x + bbox.w * padding
    patch_top = point_y - bbox.h * padding
    patch_bottom = point_y + bbox.h * padding
    patch = img[patch_top: patch_bottom + 1, patch_left: patch_right + 1]
    patch_bbox = BBox([patch_left, patch_right, patch_top, patch_bottom])
    return patch, patch_bbox


def processImage(imgs):
    """
        process images before feeding to CNNs
        imgs: N x 1 x W x H
    """
    imgs = imgs.astype(np.float32)
    for i, img in enumerate(imgs):
        imgs[i] = (img - 127.5) / 128
    return imgs


def dataArgument(data):
    """
        dataArguments
        data:
            imgs: N x 1 x W x H
            bbox: N x BBox
            landmarks: N x 10
    """
    pass


class BBox(object):
    """
        Bounding Box of face
    """

    def __init__(self, bbox):
        self.left = bbox[0]
        self.top = bbox[1]
        self.right = bbox[2]
        self.bottom = bbox[3]

        self.x = bbox[0]
        self.y = bbox[1]
        self.w = bbox[2] - bbox[0]
        self.h = bbox[3] - bbox[1]

    def expand(self, scale=0.05):
        bbox = [self.left, self.right, self.top, self.bottom]
        bbox[0] -= int(self.w * scale)
        bbox[1] += int(self.w * scale)
        bbox[2] -= int(self.h * scale)
        bbox[3] += int(self.h * scale)
        return BBox(bbox)
    # offset

    def project(self, point):
        x = (point[0] - self.x) / self.w
        y = (point[1] - self.y) / self.h
        return np.asarray([x, y])
    # absolute position(image (left,top))

    def reproject(self, point):
        x = self.x + self.w * point[0]
        y = self.y + self.h * point[1]
        return np.asarray([x, y])
    # landmark: 5*2

    def reprojectLandmark(self, landmark):
        p = np.zeros((len(landmark), 2))
        for i in range(len(landmark)):
            p[i] = self.reproject(landmark[i])
        return p
    # change to offset according to bbox

    def projectLandmark(self, landmark):
        p = np.zeros((len(landmark), 2))
        for i in range(len(landmark)):
            p[i] = self.project(landmark[i])
        return p
    #f_bbox = bbox.subBBox(-0.05, 1.05, -0.05, 1.05)
    # self.w bounding-box width
    # self.h bounding-box height

    def subBBox(self, leftR, rightR, topR, bottomR):
        leftDelta = self.w * leftR
        rightDelta = self.w * rightR
        topDelta = self.h * topR
        bottomDelta = self.h * bottomR
        left = self.left + leftDelta
        right = self.left + rightDelta
        top = self.top + topDelta
        bottom = self.top + bottomDelta
        return BBox([left, right, top, bottom])


def convert_to_square(bbox):
    """Convert bbox to square

    Parameters:
    ----------
    bbox: numpy array , shape n x 5
        input bbox

    Returns:
    -------
    square bbox
    """
    square_bbox = bbox.copy()

    h = bbox[:, 3] - bbox[:, 1] + 1
    w = bbox[:, 2] - bbox[:, 0] + 1
    max_side = np.maximum(h, w)
    square_bbox[:, 0] = bbox[:, 0] + w * 0.5 - max_side * 0.5
    square_bbox[:, 1] = bbox[:, 1] + h * 0.5 - max_side * 0.5
    square_bbox[:, 2] = square_bbox[:, 0] + max_side - 1
    square_bbox[:, 3] = square_bbox[:, 1] + max_side - 1
    return square_bbox


def IoU(box, boxes):
    """Compute IoU between detect box and gt boxes

    Parameters:
    ----------
    box: numpy array , shape (5, ): x1, y1, x2, y2, score
        input box
    boxes: numpy array, shape (n, 4): x1, y1, x2, y2
        input ground truth boxes

    Returns:
    -------
    ovr: numpy.array, shape (n, )
        IoU
    """
    box_area = (box[2] - box[0] + 1) * (box[3] - box[1] + 1)
    area = (boxes[:, 2] - boxes[:, 0] + 1) * (boxes[:, 3] - boxes[:, 1] + 1)
    xx1 = np.maximum(box[0], boxes[:, 0])
    yy1 = np.maximum(box[1], boxes[:, 1])
    xx2 = np.minimum(box[2], boxes[:, 2])
    yy2 = np.minimum(box[3], boxes[:, 3])

    # compute the width and height of the bounding box
    w = np.maximum(0, xx2 - xx1 + 1)
    h = np.maximum(0, yy2 - yy1 + 1)

    inter = w * h * 1.0
    ovr = inter / (box_area + area - inter)
    return ovr


def show_bbox(bbox, color='yellow'):
    """ Show bounding box:
        bbox = [x, y, width, height, score]
    """
    ax = plt.gca()
    if len(bbox) == 5:
        plt.text(bbox[0], bbox[1] - 6, "{:0.2f}".format(bbox[4]),
                 fontsize=16, color='magenta')
    rect = plp.Rectangle(
        (bbox[0], bbox[1]),
        bbox[2],
        bbox[3],
        fill=False, color=color, linewidth=4)
    ax.add_patch(rect)
