# coding:utf-8
import sys
# sys.path.append("../")
sys.path.insert(0, '..')
import numpy as np
import argparse
import os
import cPickle as pickle
import cv2

import train_models
from loader import TestLoader
from Detection.detector import Detector
from Detection.fcn_detector import FcnDetector
from Detection.MtcnnDetector import MtcnnDetector
from BBox_utils import IoU, convert_to_square


def read_annotation(base_dir, label_path):
    """
    read label file
    :param dir: path
    :return:
    """
    data = dict()
    images = []
    bboxes = []
    labelfile = open(label_path, 'r')
    while True:
        # image path
        imagepath = labelfile.readline().strip('\n')
        if not imagepath:
            break
        imagepath = base_dir + '/WIDER_train/images/' + imagepath
        images.append(imagepath)
        # face numbers
        nums = labelfile.readline().strip('\n')
        # im = cv2.imread(imagepath)
        # h, w, c = im.shape
        one_image_bboxes = []
        for i in range(int(nums)):
            # text = ''
            # text = text + imagepath
            bb_info = labelfile.readline().strip('\n').split(' ')
            # only need x, y, w, h
            face_box = [float(bb_info[i]) for i in range(4)]
            # text = text + ' ' + str(face_box[0] / w) + ' ' + str(face_box[1] / h)
            xmin = face_box[0]
            ymin = face_box[1]
            xmax = xmin + face_box[2]
            ymax = ymin + face_box[3]
            # text = text + ' ' + str(xmax / w) + ' ' + str(ymax / h)
            one_image_bboxes.append([xmin, ymin, xmax, ymax])
            # f.write(text + '\n')
        bboxes.append(one_image_bboxes)

    data['images'] = images  # all image pathes
    data['bboxes'] = bboxes  # all image bboxes
    # f.close()
    return data


# net : 24(RNet)/48(ONet)
# data: dict()
def save_hard_example(net, data, save_path):
    # load ground truth from annotation file
    # format of each line: image/path [x1,y1,x2,y2] for each gt_box in this
    # image

    im_idx_list = data['images']
    # print(images[0])
    gt_boxes_list = data['bboxes']
    num_of_images = len(im_idx_list)

    print("Processing %d images in total" % num_of_images)

    # save files
    neg_label_file = "%d/neg_%d.txt" % (net, image_size)
    neg_file = open(neg_label_file, 'w')

    pos_label_file = "%d/pos_%d.txt" % (net, image_size)
    pos_file = open(pos_label_file, 'w')

    part_label_file = "%d/part_%d.txt" % (net, image_size)
    part_file = open(part_label_file, 'w')
    # read detect result
    det_boxes = pickle.load(
        open(
            os.path.join(
                save_path,
                'detections.pkl'),
            'rb'))
    # print(len(det_boxes), num_of_images)
    print len(det_boxes)
    print num_of_images
    assert len(det_boxes) == num_of_images, "incorrect detections or ground truths"

    # index of neg, pos and part face, used as their image names
    n_idx = 0
    p_idx = 0
    d_idx = 0
    image_done = 0
    # im_idx_list image index(list)
    # det_boxes detect result(list)
    # gt_boxes_list gt(list)
    for im_idx, dets, gts in zip(im_idx_list, det_boxes, gt_boxes_list):
        gts = np.array(gts, dtype=np.float32).reshape(-1, 4)
        if image_done % 10000 == 0:
            print("%d images done" % image_done)
        image_done += 1

        if dets.shape[0] == 0:
            continue
        img = cv2.imread(im_idx)
        # change to square
        dets = convert_to_square(dets)
        dets[:, 0:4] = np.round(dets[:, 0:4])
        neg_num = 0
        for box in dets:
            x_left, y_top, x_right, y_bottom, _ = box.astype(int)
            width = x_right - x_left + 1
            height = y_bottom - y_top + 1

            # ignore box that is too small or beyond image border
            if width < 20 or x_left < 0 or y_top < 0 or x_right > img.shape[1] - \
                    1 or y_bottom > img.shape[0] - 1:
                continue

            # compute intersection over union(IoU) between current box and all
            # gt boxes
            Iou = IoU(box, gts)
            cropped_im = img[y_top:y_bottom + 1, x_left:x_right + 1, :]
            resized_im = cv2.resize(cropped_im, (image_size, image_size),
                                    interpolation=cv2.INTER_LINEAR)

            # save negative images and write label
            # Iou with all gts must below 0.3
            if np.max(Iou) < 0.3 and neg_num < 60:
                # save the examples
                save_file = os.path.join(neg_dir, "%s.jpg" % n_idx)
                # print(save_file)
                neg_file.write(save_file + ' 0\n')
                cv2.imwrite(save_file, resized_im)
                n_idx += 1
                neg_num += 1
            else:
                # find gt_box with the highest iou
                idx = np.argmax(Iou)
                assigned_gt = gts[idx]
                x1, y1, x2, y2 = assigned_gt

                # compute bbox reg label
                offset_x1 = (x1 - x_left) / float(width)
                offset_y1 = (y1 - y_top) / float(height)
                offset_x2 = (x2 - x_right) / float(width)
                offset_y2 = (y2 - y_bottom) / float(height)

                # save positive and part-face images and write labels
                if np.max(Iou) >= 0.65:
                    save_file = os.path.join(pos_dir, "%s.jpg" % p_idx)
                    pos_file.write(save_file + ' 1 %.2f %.2f %.2f %.2f\n' % (
                        offset_x1, offset_y1, offset_x2, offset_y2))
                    cv2.imwrite(save_file, resized_im)
                    p_idx += 1

                elif np.max(Iou) >= 0.4:
                    save_file = os.path.join(part_dir, "%s.jpg" % d_idx)
                    part_file.write(save_file + ' -1 %.2f %.2f %.2f %.2f\n' % (
                        offset_x1, offset_y1, offset_x2, offset_y2))
                    cv2.imwrite(save_file, resized_im)
                    d_idx += 1
    neg_file.close()
    part_file.close()
    pos_file.close()


def t_net(prefix, epoch, data_dir, batch_size,
          PNet_factory, RNet_factory,
          test_mode="PNet", thresh=[0.6, 0.6, 0.7], min_face_size=25,
          stride=2, slide_window=False, shuffle=False, vis=False):

    # load detectors
    detectors = [None, None, None]
    model_path = ['%s-%s' % (x, y) for x, y in zip(prefix, epoch)]

    # load pnet model
    if slide_window:
        PNet = Detector(PNet_factory, 12, batch_size[0], model_path[0])
    else:
        PNet = FcnDetector(PNet_factory, model_path[0])
    detectors[0] = PNet

    # load rnet model
    if test_mode == "RNet":
        RNet = Detector(RNet_factory, 24, batch_size[1], model_path[1])
        detectors[1] = RNet

    # Get detections
    basedir = '.'
    filename = './wider_face_train_bbx_gt.txt'
    data = read_annotation(basedir, filename)
    mtcnn_detector = MtcnnDetector(
        detectors=detectors,
        min_face_size=min_face_size,
        stride=stride,
        threshold=thresh,
        slide_window=slide_window)
    test_data = TestLoader(data['images'])
    print("Getting detections for {} images.".format(test_data.size))
    detections, _ = mtcnn_detector.detect_face(test_data)

    # Save detections
    if test_mode == "PNet":
        save_net = "RNet"
    elif test_mode == "RNet":
        save_net = "ONet"
    save_path = os.path.join(data_dir, save_net)
    if not os.path.exists(save_path):
        os.mkdir(save_path)
    save_file = os.path.join(save_path, "detections.pkl")
    with open(save_file, 'wb') as f:
        pickle.dump(detections, f, 1)

    save_hard_example(image_size, data, save_path)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Test mtcnn',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--test_mode',
        dest='test_mode',
        help='test net type, can be PNet or RNet',
        default='RNet',
        type=str)
    parser.add_argument(
        '--collaborative',
        dest='collaborative',
        help='Use collaborative MTL',
        action='store_true')
    parser.add_argument(
        '--prefix',
        dest='prefix',
        help='prefix of model name',
        nargs="+",
        default=[
            '../data/MTCNN_model/PNet_landmark/PNet',
            '../data/MTCNN_model/RNet_landmark/RNet',
            '../data/MTCNN_model/ONet_landmark/ONet'],
        type=str)
    parser.add_argument(
        '--epoch',
        dest='epoch',
        help='epoch number of model to load',
        nargs="+",
        default=[
            70,
            70,
            70],
        type=int)
    parser.add_argument(
        '--batch_size',
        dest='batch_size',
        help='list of batch size used in prediction',
        nargs="+",
        default=[
            2048,
            256,
            16],
        type=int)
    parser.add_argument(
        '--thresh',
        dest='thresh',
        help='list of thresh for pnet, rnet, onet',
        nargs="+",
        default=[
            0.4,
            0.05,
            0.7],
        type=float)
    parser.add_argument(
        '--min_face',
        dest='min_face',
        help='minimum face size for detection',
        default=24,
        type=int)
    parser.add_argument(
        '--stride',
        dest='stride',
        help='stride of sliding window',
        default=2,
        type=int)
    parser.add_argument(
        '--sw',
        dest='slide_window',
        help='use sliding window in pnet',
        action='store_true')
    parser.add_argument(
        '--shuffle',
        dest='shuffle',
        help='shuffle data on visualization',
        action='store_true')
    args = parser.parse_args()
    return args


if __name__ == '__main__':

    args = parse_args()
    print(args)

    model_prefix = args.prefix

    if args.collaborative:
        print("Using collaborative MTL.")
        model_prefix = [s.replace('MTCNN_model', 'MTCNN_collaborative_model') for s in model_prefix]
        PNet_factory = train_models.mtcnn_collaborative_model.P_Net
        RNet_factory = train_models.mtcnn_collaborative_model.R_Net
    else:
        PNet_factory = train_models.mtcnn_model.P_Net
        RNet_factory = train_models.mtcnn_model.R_Net

    if args.test_mode == "PNet":
        image_size = 24
    elif args.test_mode == "RNet":
        image_size = 48
    else:
        raise Exception("Invalid test_mode: {}".format(args.test_mode))

    base_dir = '../prepare_data/WIDER_train'
    data_dir = '%s' % str(image_size)

    neg_dir = os.path.join(data_dir, 'negative')
    pos_dir = os.path.join(data_dir, 'positive')
    part_dir = os.path.join(data_dir, 'part')

    # create dictionary shuffle
    for dir_path in [neg_dir, pos_dir, part_dir]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

    t_net(model_prefix,  # model param's file
          args.epoch,  # final epoches
          data_dir,
          args.batch_size,  # test batch_size
          PNet_factory,
          RNet_factory,
          args.test_mode,  # test which model
          args.thresh,  # cls threshold
          args.min_face,  # min_face
          args.stride,  # stride
          args.slide_window,
          args.shuffle,
          vis=False)
