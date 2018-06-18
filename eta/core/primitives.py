'''
Implementations of computer vision primitive algorithms.

Copyright 2018, Voxel51, LLC
voxel51.com

Brian Moore, brian@voxel51.com
Kunyi Lu, kunyi@voxel51.com
'''
# pragma pylint: disable=redefined-builtin
# pragma pylint: disable=unused-wildcard-import
# pragma pylint: disable=wildcard-import
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from builtins import *
# pragma pylint: enable=redefined-builtin
# pragma pylint: enable=unused-wildcard-import
# pragma pylint: enable=wildcard-import

import cv2
import numpy as np

import eta.core.utils as etau
import eta.core.video as etav


class DenseOpticalFlow(object):
    '''Base class for dense optical flow methods.'''

    def process(
            self, input_path, cart_path=None, polar_path=None, vid_path=None):
        '''Performs dense optical flow on the given video.

        Args:
            input_path: the input video path
            cart_path: an optional path to write the per-frame arrays as .npy
                files describing the flow fields in Cartesian (x, y)
                coordinates
            polar_path: an optional path to write the per-frame arrays as .npy
                files describing the flow fields in polar (magnitude, angle)
                coordinates
            vid_path: an optional path to write a video that visualizes the
                magnitude and angle of the flow fields as the value (V) and
                hue (H), respectively, of per-frame HSV images
        '''
        # Ensure output directories exist
        if cart_path:
            etau.ensure_basedir(cart_path)
        if polar_path:
            etau.ensure_basedir(polar_path)
        # VideoProcessor ensures that the output video directory exists

        self._reset()
        with etav.VideoProcessor(input_path, out_single_vidpath=vid_path) as p:
            for img in p:
                # Compute optical flow
                flow_cart = self._process_frame(img)

                if cart_path:
                    # Write Cartesian fields
                    np.save(cart_path % p.frame_number, flow_cart)

                if not polar_path and not vid_path:
                    continue

                # Convert to polar coordinates
                mag, ang = cv2.cartToPolar(
                    flow_cart[..., 0], flow_cart[..., 1])
                flow_polar = np.dstack((mag, ang))

                if polar_path:
                    # Write polar fields
                    np.save(polar_path % p.frame_number, flow_polar)

                if vid_path:
                    # Write flow visualization frame
                    p.write(_polar_flow_to_img(mag, ang))

    def _process_frame(self, img):
        '''Processes the next frame.

        Args:
            img: the next frame

        Returns:
            flow: the optical flow for the frame in Cartesian coordinates
        '''
        raise NotImplementedError("subclass must implement _process_frame()")

    def _reset(self):
        '''Prepares the object to start processing a new video.'''
        pass


def _polar_flow_to_img(mag, ang):
    hsv = np.zeros(mag.shape + (3,), dtype=mag.dtype)
    hsv[..., 0] = (89.5 / np.pi) * ang  # [0, 179]
    hsv[..., 1] = 255
    #hsv[..., 2] = np.minimum(255 * mag, 255)  # [0, 255]
    hsv[..., 2] = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX)  # [0, 255]
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


class FarnebackDenseOpticalFlow(DenseOpticalFlow):
    '''Computes dense optical flow on a video using Farneback's method.

    This class is a wrapper around the OpenCV `calcOpticalFlowFarneback`
    function.
    '''

    def __init__(
            self,
            pyramid_scale=0.5,
            pyramid_levels=3,
            window_size=15,
            iterations=3,
            poly_n=7,
            poly_sigma=1.5,
            use_gaussian_filter=False):
        '''Constructs a FarnebackDenseOpticalFlow object.

        Args:
            pyramid_scale (0.5): the image scale (<1) to build pyramids for
                each image
            pyramid_levels (3): number of pyramid layers including the initial
                image
            window_size (15): averaging window size
            iterations (3): number of iterations to perform at each pyramid
                level
            poly_n (7): size of the pixel neighborhood used to find polynomial
                expansion in each pixel
            poly_sigma (1.5): standard deviation of the Gaussian that is used
                to smooth derivatives
            use_gaussian_filter (False): whether to use a Gaussian filter
                instead of a box filer
        '''
        self.pyramid_scale = pyramid_scale
        self.pyramid_levels = pyramid_levels
        self.window_size = window_size
        self.iterations = iterations
        self.poly_n = poly_n
        self.poly_sigma = poly_sigma
        self.use_gaussian_filter = use_gaussian_filter

        self._prev_frame = None
        self._flags = (
            cv2.OPTFLOW_FARNEBACK_GAUSSIAN if use_gaussian_filter else 0)

    def _process_frame(self, img):
        curr_frame = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if self._prev_frame is None:
            # There is no previous frame for the first frame, so we set
            # it to the current frame, which implies that the flow for
            # the first frame will always be zero
            self._prev_frame = curr_frame

        # works in OpenCV 3 and OpenCV 2
        flow_cart = cv2.calcOpticalFlowFarneback(
            self._prev_frame, curr_frame, flow=None,
            pyr_scale=self.pyramid_scale, levels=self.pyramid_levels,
            winsize=self.window_size, iterations=self.iterations,
            poly_n=self.poly_n, poly_sigma=self.poly_sigma,
            flags=self._flags)
        self._prev_frame = curr_frame

        return flow_cart

    def _reset(self):
        self._prev_frame = None


class BackgroundSubtractor(object):
    '''Base class for background subtraction methods.'''

    def process(
            self, input_path, fgmask_path=None, fgvid_path=None,
            bgvid_path=None):
        '''Performs background subtraction on the given video.

        Args:
            input_path: the input video path
            fgmask_path: an optional path to write the per-frame foreground
                masks as .npy files
            fgvid_path: an optional path to write the foreground-only video
            bgvid_path: an optional path to write the background video
        '''
        # Ensure output directories exist
        if fgmask_path:
            etau.ensure_basedir(fgmask_path)
        # VideoWriters ensure that the output video directories exist

        r = etav.FFmpegVideoReader(input_path)
        try:
            if fgvid_path:
                fgw = etav.FFmpegVideoWriter(
                    fgvid_path, r.frame_rate, r.frame_size)
            if bgvid_path:
                bgw = etav.FFmpegVideoWriter(
                    bgvid_path, r.frame_rate, r.frame_size)

            self._reset()
            for img in r:
                fgmask, bgimg = self._process_frame(img)

                if fgmask_path:
                    # Write foreground mask
                    np.save(fgmask_path % r.frame_number, fgmask)

                if fgvid_path:
                    # Write foreground-only video
                    img[np.where(fgmask == 0)] = 0
                    fgw.write(img)

                if bgvid_path:
                    # Write background video
                    bgw.write(bgimg)
        finally:
            if fgvid_path:
                fgw.close()
            if bgvid_path:
                bgw.close()

    def _process_frame(self, img):
        '''Processes the next frame.

        Args:
            img: the next frame

        Returns:
            fgmask: the foreground mask
            bgimg: the background-only image
        '''
        raise NotImplementedError("subclass must implement _process_frame()")

    def _reset(self):
        '''Prepares the object to start processing a new video.'''
        pass


class BackgroundSubtractorError(Exception):
    '''Error raised when an error is encountered while performing background
    subtraction.
    '''
    pass


class MOG2BackgroundSubtractor(BackgroundSubtractor):
    '''Performs background subtraction on a video using Gaussian mixture-based
    foreground-background segmentation.

    This class is a wrapper around the OpenCV `BackgroundSubtractorMOG2` class.

    This model is only supported when using OpenCV 3.
    '''

    def __init__(
            self, history=500, threshold=16.0, learning_rate=-1,
            detect_shadows=False):
        '''Initializes an MOG2BackgroundSubtractor object.

        Args:
            history (500): the number of previous frames that affect the
                background model
            threshold (16.0): threshold on the squared Mahalanobis distance
                between pixel and the model to decide whether a pixel is well
                described by the background model
            learning_rate (-1): a value between 0 and 1 that indicates how fast
                the background model is learnt, where 0 means that the
                background model is not updated at all and 1 means that the
                background model is completely reinitialized from the last
                frame. If a negative value is provided, an automatically chosen
                learning rate will be used
            detect_shadows (True): whether to detect and mark shadows
        '''
        self.history = history
        self.threshold = threshold
        self.learning_rate = learning_rate
        self.detect_shadows = detect_shadows
        self._fgbg = None

    def _process_frame(self, img):
        fgmask = self._fgbg.apply(img, None, self.learning_rate)
        bgimg = self._fgbg.getBackgroundImage()
        return fgmask, bgimg

    def _reset(self):
        try:
            # OpenCV 3
            self._fgbg = cv2.createBackgroundSubtractorMOG2(
                history=self.history, varThreshold=self.threshold,
                detectShadows=self.detect_shadows)
        except AttributeError:
            # OpenCV 2
            #
            # Note that OpenCV 2 does have a BackgroundSubtractorMOG2 class,
            # but background subtractors in OpenCV 2 don't support the
            # getBackgroundImage method, so they are not suitable for our
            # interface here
            #
            raise BackgroundSubtractorError(
                "BackgroundSubtractorMOG2 is not supported in OpenCV 2")


class KNNBackgroundSubtractor(BackgroundSubtractor):
    '''Performs background subtraction on a video using K-nearest
    neighbors-based foreground-background segmentation.

    This class is a wrapper around the OpenCV `BackgroundSubtractorKNN` class.

    This model is only supported when using OpenCV 3.
    '''

    def __init__(
            self, history=500, threshold=400.0, learning_rate=-1,
            detect_shadows=False):
        '''Initializes an KNNBackgroundSubtractor object.

        Args:
            history (500): length of the history
            threshold (400.0): threshold on the squared distance between pixel
                and the sample to decide whether a pixel is close to that
                sample
            learning_rate (-1): a value between 0 and 1 that indicates how fast
                the background model is learnt, where 0 means that the
                background model is not updated at all and 1 means that the
                background model is completely reinitialized from the last
                frame. If a negative value is provided, an automatically chosen
                learning rate will be used
            detect_shadows (True): whether to detect and mark shadows
        '''
        self.history = history
        self.threshold = threshold
        self.learning_rate = learning_rate
        self.detect_shadows = detect_shadows
        self._fgbg = None

    def _process_frame(self, img):
        fgmask = self._fgbg.apply(img, None, self.learning_rate)
        bgimg = self._fgbg.getBackgroundImage()
        return fgmask, bgimg

    def _reset(self):
        try:
            # OpenCV 3
            self._fgbg = cv2.createBackgroundSubtractorKNN(
                history=self.history, dist2Threshold=self.threshold,
                detectShadows=self.detect_shadows)
        except AttributeError:
            # OpenCV 2
            raise BackgroundSubtractorError(
                "KNNBackgroundSubtractor is not supported in OpenCV 2")


class EdgeDetector(object):
    '''Base class for edge detection methods.'''

    def process(self, input_path, masks_path=None, vid_path=None):
        '''Detect edges using self.detector.

        Args:
            input_path: the input video path
            masks_path: an optional path to write the per-frame edge masks as
                .npy files
            vid_path: an optional path to write the edges video
        '''
        # Ensure output directories exist
        if masks_path:
            etau.ensure_basedir(masks_path)
        # VideoProcessor ensures that the output video directory exists

        self._reset()
        with etav.VideoProcessor(input_path, out_single_vidpath=vid_path) as p:
            for img in p:
                # Compute edges
                edges = self._process_frame(img)

                if masks_path:
                    # Write edges mask
                    np.save(masks_path % p.frame_number, edges.astype(np.bool))

                if vid_path:
                    # Write edges video
                    p.write(cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR))

    def _process_frame(self, img):
        '''Processes the next frame.

        Args:
            img: the next frame

        Returns:
            edges: the edges image
        '''
        raise NotImplementedError("subclass must implement _process_frame()")

    def _reset(self):
        '''Prepares the object to start processing a new video.'''
        pass


class CannyEdgeDetector(EdgeDetector):
    '''The Canny edge detector.

    This class is a wrapper around the OpenCV `Canny` method.
    '''

    def __init__(
            self, threshold1=200, threshold2=50, aperture_size=3,
            l2_gradient=False):
        '''Creates a new CannyEdgeDetector object.

        Args:
            threshold1 (200): the edge threshold
            threshold2 (50): the hysteresis threshold
            aperture_size (3): aperture size for the Sobel operator
            l2_gradient (False): whether to use a more accurate L2 norm to
                calculate the image gradient magnitudes
        '''
        self.threshold1 = threshold1
        self.threshold2 = threshold2
        self.aperture_size = aperture_size
        self.l2_gradient = l2_gradient

    def _process_frame(self, img):
        # works in OpenCV 3 and OpenCV 2
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return cv2.Canny(
            gray, threshold1=self.threshold1, threshold2=self.threshold2,
            apertureSize=self.aperture_size, L2gradient=self.l2_gradient)


class FeaturePointDetector(object):
    '''Base class for feature point detection methods.'''

    KEYPOINT_DRAW_COLOR = (0, 255, 0)

    def process(self, input_path, coords_path=None, vid_path=None):
        '''Detect feature points using self.detector.

        Args:
            input_path: the input video path
            masks_path: an optional path to write the per-frame feature points
                as .npy files
            vid_path: an optional path to write the feature points video
        '''
        # Ensure output directories exist
        if coords_path:
            etau.ensure_basedir(coords_path)
        # VideoProcessor ensures that the output video directory exists

        self._reset()
        with etav.VideoProcessor(input_path, out_single_vidpath=vid_path) as p:
            for img in p:
                # Compute feature points
                keypoints = self._process_frame(img)

                if coords_path:
                    # Write feature points to disk
                    pts = _unpack_keypoints(keypoints)
                    np.save(coords_path % p.frame_number, pts)

                if vid_path:
                    # Write feature points video
                    img = cv2.drawKeypoints(
                        img, keypoints, None, color=self.KEYPOINT_DRAW_COLOR)
                    p.write(img)

    def _process_frame(self, img):
        '''Processes the next frame.

        Args:
            img: the next frame

        Returns:
            keypoints: a list of `cv2.KeyPoint`s describing the detected
                features
        '''
        raise NotImplementedError("subclass must implement _process_frame()")

    def _reset(self):
        '''Prepares the object to start processing a new video.'''
        pass


class HarrisFeaturePointDetector(FeaturePointDetector):
    '''Detects Harris corners.

    This class is a wrapper around the OpenCV `cornerHarris` method.
    '''

    def __init__(self, threshold=0.01, block_size=3, aperture_size=3, k=0.04):
        '''Creates a new HarrisEdgeDetector object.

        Args:
            threshold (0.01): threshold (relative to the maximum detector
                response) to declare a corner
            block_size (3): the size of neighborhood used for the Harris
                operator
            aperture_size (3): aperture size for the Sobel derivatives
            k (0.04): Harris detector free parameter
        '''
        self.threshold = threshold
        self.block_size = block_size
        self.aperture_size = aperture_size
        self.k = k

    def _process_frame(self, img):
        # works in OpenCV 3 and OpenCV 2
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = np.float32(gray)
        response = cv2.cornerHarris(
            gray, blockSize=self.block_size, ksize=self.aperture_size,
            k=self.k)
        response = cv2.dilate(response, None)
        corners = response > self.threshold * response.max()
        return _pack_keypoints(np.argwhere(corners))


class FASTFeaturePointDetector(FeaturePointDetector):
    '''Detects feature points using the FAST method.

    This class is a wrapper around the OpenCV `FastFeatureDetector` class.
    '''

    def __init__(self, threshold=1, non_max_suppression=True):
        '''Creates a new FastFeatureDetector instance.

        Args:
            threshold (1): threshold on difference between intensity of the
                central pixel and pixels of a circle around this pixel
            non_max_suppression (True): whether to apply non-maximum
                suppression to the detected keypoints
        '''
        self.threshold = threshold
        self.non_max_suppression = non_max_suppression
        try:
            # OpenCV 3
            self._detector = cv2.FastFeatureDetector(
                threshold=self.threshold,
                nonmaxSuppression=self.non_max_suppression)
        except AttributeError:
            # OpenCV 2
            self._detector = cv2.FastFeatureDetector_create(
                threshold=self.threshold,
                nonmaxSuppression=self.non_max_suppression)

    def _process_frame(self, img):
        return self._detector.detect(img, None)


class ORBFeaturePointDetector(FeaturePointDetector):
    '''Detects feature points using the ORB (Oriented FAST and rotated BRIEF
    features) method.

    This class is a wrapper around the OpenCV `ORB` class.
    '''

    def __init__(self, max_num_features=500, score_type=cv2.ORB_HARRIS_SCORE):
        '''Creates a new ORBFeaturePointDetector instance.

        Args:
            max_num_features (500): the maximum number of features to retain
            score_type (cv2.ORB_HARRIS_SCORE): the algorithm used to rank
                features. The choices are `cv2.ORB_HARRIS_SCORE` and
                `cv2.FAST_SCORE`
        '''
        self.max_num_features = max_num_features
        self.score_type = score_type
        try:
            # OpenCV 3
            self._detector = cv2.ORB_create(
                nfeatures=self.max_num_features, scoreType=self.score_type)
        except AttributeError:
            # OpenCV 2
            self._detector = cv2.ORB(
                nfeatures=self.max_num_features, scoreType=self.score_type)

    def _process_frame(self, img):
        return self._detector.detect(img, None)


def _pack_keypoints(pts):
    '''Pack the points into a list of `cv2.KeyPoint`s.

    Args:
        pts: an n x 2 array of [row, col] coordinates

    Returns:
        a list of `cv2.KeyPoint`s
    '''
    return [cv2.KeyPoint(x[1], x[0], 1) for x in pts]


def _unpack_keypoints(keypoints):
    '''Unpack the keypoints into an array of coordinates.

    Returns:
        keypoints: a list of `cv2.KeyPoint`s

    Args:
        an n x 2 array of [row, col] coordinates
    '''
    return np.array([[kp.pt[1], kp.pt[0]] for kp in keypoints])