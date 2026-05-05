"""
Camera Controller Module

This module owns the USB webcam capture loop. A background thread reads frames
from OpenCV as fast as the camera provides them, and request handlers pull a
copy of the most recent frame whenever the browser asks for video.
"""

import cv2
import logging
from threading import Thread, Lock

logger = logging.getLogger(__name__)


class CameraController:
    """Capture frames continuously and expose the latest frame to callers."""
    
    def __init__(self, camera_index=0, width=640, height=480, fps=30):
        """
        Initialize camera controller
        
        Args:
            camera_index: OpenCV camera index (0 for /dev/video0)
            width: Frame width in pixels
            height: Frame height in pixels
            fps: Target frames per second
        """
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.fps = fps
        self.frame = None
        self.frame_lock = Lock()
        self.running = False
        self.capture_thread = None
        self.cap = None
        
        self._init_camera()
        self._start_capture()
    
    def _init_camera(self):
        """Open the camera and configure low-latency capture settings."""
        try:
            self.cap = cv2.VideoCapture(self.camera_index)
            
            if not self.cap.isOpened():
                logger.error(f"Failed to open camera at index {self.camera_index}")
                return
            
            # Request the desired capture settings. The device may not honor
            # every value exactly, but these calls express the intended mode.
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer for lower latency
            
            logger.info(f"Camera initialized: {self.width}x{self.height} @ {self.fps} FPS")
            
        except Exception as e:
            logger.error(f"Camera initialization error: {e}")
            self.cap = None
    
    def _start_capture(self):
        """Start the background capture loop if camera initialization succeeded."""
        if self.cap is None:
            logger.warning("Cannot start capture - camera not initialized")
            return
        
        self.running = True
        self.capture_thread = Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        logger.info("Camera capture thread started")
    
    def _capture_loop(self):
        """Continuously refresh the latest frame buffer from the camera."""
        while self.running:
            try:
                ret, frame = self.cap.read()
                
                if ret:
                    with self.frame_lock:
                        self.frame = frame
                else:
                    logger.warning("Failed to read frame from camera")
                    
            except Exception as e:
                logger.error(f"Error in capture loop: {e}")
    
    def get_frame(self):
        """Return a copy of the latest captured frame, if one is available."""
        with self.frame_lock:
            if self.frame is not None:
                return self.frame.copy()
            return None
    
    def is_running(self):
        """Check if camera is actively capturing"""
        return self.running and self.cap is not None and self.cap.isOpened()
    
    def release(self):
        """Stop capture and release the OpenCV device handle."""
        self.running = False
        
        if self.capture_thread:
            self.capture_thread.join(timeout=2)
        
        if self.cap:
            self.cap.release()
            logger.info("Camera released")
    
    def __del__(self):
        """Cleanup when object is destroyed"""
        self.release()
