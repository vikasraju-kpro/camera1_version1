import cv2
from common.camera_controller import initialize_camera, cleanup
from picamera2 import Picamera2 # We need a direct instance
import matplotlib.pyplot as plt

# Initialize
picam = Picamera2(0)
picam.create_preview_configuration()
picam.start()
time.sleep(2)

# Get a frame
array_bgr = picam.capture_array("main")

# Convert it to RGB for display
if array_bgr.shape[2] == 4:
    array_rgb = cv2.cvtColor(array_bgr, cv2.COLOR_BGRA2RGB)
else:
    array_rgb = cv2.cvtColor(array_bgr, cv2.COLOR_BGR2RGB)

print("Displaying a single live frame. If colors are correct, the camera capture is good.")
plt.imshow(array_rgb)
plt.title("Live Frame Verification")
plt.show()

# Cleanup
picam.stop()