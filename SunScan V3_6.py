# SHG 700 basic scanning script
#
# This script scans the Sun on the RA axis, using timed mount movements.
# For development, I'm assuming I'll be using the following equipment:
#  -- SAL-33 mount
#  -- Askar 80ED telescope: 80mm aperture, 560mm focal length
#  -- SHG-700 spectroheliograph with 7mm slit
#  -- QHY5III678M camera: 3856x2180 with 2 micron square pixels (7.71mm x 4.36mm)
#  -- Sol Searcher sun finder
#
# The combination of telescope and camera gives an image scale of
# (2/560) x 206.265 = 0.737 arc-sec/pixel = 368.5 arc-sec/mm
#   3856 pixels -- 7.71 mm -- 2841.87 arc-sec 
#	2180 pixels -- 4.36 mm -- 1606.66 arc-sec
# The Sun's diameter ranges from 1896 arc-sec to 1962 arc-sec (5.14 mm to 5.23 mm).
# So, the SHG 700 slit ranges from 134% to 136% of the Sun's diameter.  If we want
# a square scan, then we want a scan margin of about 35%.
# Note: After much use, I find that produces excessively large .ser files. Perhaps
# 25% would be more reasonable.
#
#
# V3:	1)	Implemented limb detection based on Christian Bennich's script.
#		2)	Added a test function, "sun_on_slit", including a button on
#			the SharpCap menu. 
#
# V3.1:	1) 	Added de-centering -- move Eastward by half the Sun's diameter to 
#			aid moving from an estimated disk center to the East limb
#		2)	Moved scan time reporting to the "run_single_scan" function
#
# V3.2:	1)	Fixed bug in "find_limb" function; the function would skip moving back
#			back to the limb after moving off the disk.
#		2)	Moved "Maximum exposure" report to its own line.
#		3)	Added convenience functions and shortcuts: "scan_from_limb" (sl)
#			and "scan_from_center" (sc).
#		4)	Added a parameter to the "run_single_scan" function to select between moving
#			to the estimated center of the Sun's disk or to the initial scanning position
#			after the scan is complete.
#
# V3.3:	1)	Added "return_to_start" parameter to "scan_from_limb" function. This allows
#			the "scan_from_center" function to return to the center of the Sun's disk.
#		2)	Added more convenience shortcuts based on Item 1 changes. 
#
# V3.4:	1)	Changed the scan process to make it easier to select starting and ending the
#			scan on the Sun's disk. This allows easier adjustment in Dec in the dwell
#			period between scans.
#		2)	Added an "enable_statistics" parameter to the FrameGrabber class to inhibit 
#			statistics calculations without detaching the class instance.
#
# V3.5:	1)	Added a function to move from nominal start scan point to the center of the
#			Sun's disk. This allows the user to leave the telescope off the disk, reducing
#			heat build-up on the SHG.
#		2)	Fixed bug in "run_single_scan" function -- return_to_start handling logic
#			was inverted.
#
# V3.6:	1)	General cleanup
#			a) Change scan count and delay parameters to constants and delete setters.
#			b) Improve status reporting 
#
# -------------------------------------------------------------------------------
#	Written by Tim Cole, for my own use.
#	I've found this script handy for using my SHG, so I'm making it available
#	to other SHG and SharpCap users. If you find it useful, that's great.
#	While the Creative Commons licenses aren't intended for software or hardware,
#	the intent of the CC BY-SA-NC license is exactly what I have in mind.
#	(See: https://creativecommons.org/licenses/by-nc-sa/4.0/deed.en)
#
#	And, of course, I have to add the usual disclaimers. This script is
#	made available without any guarantees or warranties. You are completely
# 	responsible for making sure this script will be suitable for your own uses and 
#	to ensure that using the script won't cause any damage to your equipment or
#	injury to yourself or others. 
#
# -------------------------------------------------------------------------------

import clr
import datetime
import time
import math
clr.AddReference("System.Drawing")
from System.Drawing import Bitmap
import SolarData

#-------------------------------------------------------------------------------
# Constants

VERSION = 3.6 

# Note: The term "rate" gets overloaded in SHG scanning. The mount control system
# in SharpCap uses "rate" to mean multiples of the sidereal rate
# (i.e. 15.04 arc-sec/sec). To avoid potential confusion, I'm using the term
# "speed" to indicate arc-sec/sec.

SIDEREAL_SPEED = 15.04 # arc-sec/sec
ARC_SEC_PER_HOUR = 54000.0  # Angular hours (15 x 3600)
RA_AXIS = 0
DEC_AXIS = 1

# The following constants are based on observed behavior on SharpCap with the SAL-33
# MoveAxis(0, +xxx) -> RA decreases, as reported on mount control panel
# MoveAxis(0, -xxx) -> RA increases, as reported on mount control panel

WESTWARD = +1.0
EASTWARD = -1.0

SCRIPT_PATH = "C:\\Imaging\\SharpCap Scripts\\Scan Automation"
#SCRIPT_PATH = "D:\\SharpCap Scripts\\Scan Automation"
#SCRIPT_PATH = "D:\\Projects\\Spectroheliograph Projects\\Scan Automation"

mount = SharpCap.Mounts.SelectedMount
camera = SharpCap.SelectedCamera

#-------------------------------------------------------------------------------
# Scanning parameters -- revise as needed

PIXEL_SIZE = 2.0 # QHY5III678M
FOCAL_LENGTH = 560 # Askar 80ED
# FOCAL_LENGTH = 700 # Askar 103APO
SCAN_MARGIN = 0.25
RECENTER_RATE = 16.0
OFFSET_RATE = 16.0
SETTLING_TIME = 0.5
SCAN_COUNT = 2
SCAN_DELAY = 10
#-------------------------------------------------------------------------------
# Limb detection parameters 
#
# Limb detection works by examining a series of intercepted frames for standard
# deviation rather than mean brightness, an approach shown to work in Christian
# Bennich's "Fast Burst Scanner V2" script and Patrick Hsieh's "SHGScan" script.
# On the Sun's disk, absorption lines vary the overall brightness irregularly,
# but the standard deviation is high. Off disk, there are still absorption lines,
# but the overall frame level is much lower. Therefore, an off-disk frame will have
# a low standard deviation. Bennich's and Hsieh's scripts demonstrate that standard
# deviation is a robust limb detection criterion. 
#
# Bennich reports that the sensor dark noise standard deviation for an IMX678 based
# camera in the MONO16 color space is typically between 20 and 100. On-disk standard
# deviation is greater than 10,000. A standard deviation of 500 would seem to be
# Bennich's estimated level for a frame that is straddling the limb, with only part
# of the frame on-disk. I'll go with his number.
#
# From Patrick Hsieh's correspondence with Robin Glover on the SharpCap forum:
# 1) The Frame.GetStats() method returns an object with two elements:
# Frame.Item1 (brightness) and Frame.Item2 (standard deviation). It seems that
# GetStats() calculates those values for the ROI only.
# 2) SharpCap raises a "FrameCaptured" event when it captures a frame. The handler must
# be kept short, as SharpCap is blocked while the handler executes.
#
 
LIMB_SEARCH_RATE = 8.0 # x sidereal
LIMB_SAMPLE_INTERVAL = 0.05 # seconds
LIMB_SEARCH_TIMEOUT = 120 # seconds
LIMB_SIGMA = 500
	# standard deviation to indicate limb crossing.
DISK_SIGMA = 2000
	# Standard deviation above this shows that the slit is definitely on the disk 
LIMB_SIGMA_MULTIPLE = 5.0
	# Multiplier for comparison to the observed dark background.
	
#-------------------------------------------------------------------------------

class FrameGrabber:
	""" Class for frame grabbing and analysis """
	
	def __init__(self, camera): 
		self._camera = camera
		self._attached = False
		self._enabled = False
		self._mean_brightness = 0.0
		self._standard_deviation = 0.0
		
	def attach(self):
		self._camera.FrameCaptured += self._on_capture
		time.sleep(0.25)
		self._attached = True
		self._enabled = True
		return self._attached

	def detach(self):
		if self._attached:
			self._camera.FrameCaptured -= self._on_capture
			self._attached = False
			self._enabled = False
			return self._attached
	
	def enable_stats(self):
		if self._attached:
			self._enabled = True
		return self._enabled
		
	def disable_stats(self):
		self._enabled = False
		return self._enabled

	def _on_capture(self, sender, args):
		if self._attached and self._enabled:
			stats = args.Frame.GetStats()
			self._mean_brightness = stats.Item1
			self._standard_deviation = stats.Item2
		return

	@property
	def attached(self):
		return self._attached

	@property
	def stats_enabled(self):
		return self._enabled

	@property
	def mean_brightness(self):
		return (self._mean_brightness if (self._attached and self._enabled) else 0.0)

	@property
	def standard_deviation(self):
		return (self._standard_deviation if (self._attached and self._enabled) else 0.0)

#-------------------------------------------------------------------------------
# Utility functions


def start_image_capture():
	camera.PrepareToCapture()
	camera.RunCapture()
		
def calculate_scan_rate(image_scale, frame_rate):
	scan_speed = image_scale * frame_rate # arc-sec/sec
	scan_rate = scan_speed / SIDEREAL_SPEED # x sidereal rate
	return(scan_rate, scan_speed)

def setup_scan():
	""" Calculate required mount scan rate from live frame rate. Each frame
		contributes 1 line to the final image, analogous to one pixel.
		image_scale * frame_rate -> arc-sec/pixel  * "pixels"/sec -> arc-sec/sec
		
		Note: Re-run this function after changing the size of the ROI.
	"""
	global sun_diameter
	global scan_length
	global scan_time
	global offset_time
	global recenter_time
	global limb_search_time
	global scan_rate_actual

	# Get the frame rate and calculate the required scan rate for unity X/Y ratio.
	frame_rate = camera.CurrentFrameRate
	image_scale = (PIXEL_SIZE / FOCAL_LENGTH) * 206.265
		# arc-sec/radian divided by 1000 to compensate for pixel sixe in microns
	scan_rate_actual, scan_speed_actual = calculate_scan_rate(image_scale, frame_rate)
	
	# Get the Sun's diameter and calculate the total scan length and scan times.
	sun_diameter = SolarData.get_sun_diameter()	
	margin_length = sun_diameter * SCAN_MARGIN / 2.0
	scan_length = sun_diameter * (1.0 + SCAN_MARGIN)
	scan_time = scan_length / (scan_rate_actual * SIDEREAL_SPEED)
	offset_time = margin_length / (OFFSET_RATE * SIDEREAL_SPEED)
		# time to move from limb to starting position
	recenter_time = scan_length / (RECENTER_RATE * SIDEREAL_SPEED) / 2.0
		# estimated time to move from scan end to mid-disk, including a fudge factor
	limb_search_time = ((sun_diameter / 2.0) / (LIMB_SEARCH_RATE * SIDEREAL_SPEED)) * 1.15
	print("")
	print("Current scan parameters")
	print("=======================")
	print("")
	print("Sun's diameter: {:.1f} arc-sec".format(sun_diameter))
	print("Scan margin: ", int(SCAN_MARGIN * 100), "%")
	print("Scan length: {:.2f} arc-sec".format(scan_length))
	print("Limb search rate: {:.1f} x sidereal -> {:.2f} arc-sec/sec".format(LIMB_SEARCH_RATE, (LIMB_SEARCH_RATE * SIDEREAL_SPEED)))
	print("Offset rate: {:.1f} x sidereal -> {:.2f} arc-sec/sec".format(OFFSET_RATE, (OFFSET_RATE * SIDEREAL_SPEED)))
	print("Recenter rate: {:.1f} x sidereal -> {:.2f} arc-sec/sec".format(RECENTER_RATE, (RECENTER_RATE * SIDEREAL_SPEED)))
	print("")	
	print("Reported frame rate: {:.2f} FPS".format(frame_rate))
	print("Maximum exposure: {:.2f} ms".format((1000.0 / frame_rate)))
	print("Image scale: {:.3f} arc-sec/pixel".format(image_scale))
	print("Calculated scan rate: {:.2f} x sidereal -> {:.2f} arc-sec/sec".format(scan_rate_actual, scan_speed_actual))
	print("")
	print("Scan time: {:.1f} sec".format(scan_time))
	print("Limb search time: {:.1f} sec (estimated)".format(limb_search_time))
	print("Recenter time: {:.1f} sec".format(recenter_time))
	print("Offset time: {:.1f} sec".format(offset_time))
	print("Inter-scan delay: {:.1f} sec".format(SCAN_DELAY))
	print("Cycle time: {:.1f} sec (estimated)".format((scan_time + limb_search_time + recenter_time + offset_time + SCAN_DELAY)))
	print("")
	print("=======================")
	print("")
	mount.TrackingRate = mount.TrackingRate.Solar
	time.sleep(SETTLING_TIME)
	if not mount.Tracking:
		print("Mount not responding")
	else:
		print("Tracking at solar rate")
		print("")
		print("=======================")
		print("")

def sun_on_slit():
	"""	Use the frame's standard deviation to see if the Sun's disk is on the the slit
		Requirements before calling:
		1)	The caller is responsible for attaching the FrameStatistics instance to SharpCap.
		2)	The caller is responsible for enabling statistics collection.
	"""
	print("Mean Brightness: {:.3f}   Sigma: {:.2f}".format(FrameStatistics.mean_brightness, FrameStatistics.standard_deviation))
	on_disk = FrameStatistics.standard_deviation >= DISK_SIGMA
	print("Slit is {}".format("on disk" if on_disk else "off disk"))
	return on_disk

def find_limb():
	""" Search for the Sun's limb by checking changes in frame
		standard deviation.
		Requirements before calling:
		1)	The Sun's disk should be on the slit before calling find_limb.
		2)	The caller is responsible for attaching the FrameStatistics instance to SharpCap.
		3)	The caller is responsible for enabling statistics collection.
	"""
	if FrameStatistics.standard_deviation < DISK_SIGMA:
		print("Place slit on disk before calling find_limb")
		return False

	print("Searching for East limb....")

	# Move Eastward until slit is off disk
	off_disk = False
	mount.MoveAxis(RA_AXIS, (EASTWARD * LIMB_SEARCH_RATE))
	phase_start = time.time()
	time_0 = phase_start
	while (time.time() - phase_start) < LIMB_SEARCH_TIMEOUT:
		if FrameStatistics.standard_deviation < LIMB_SIGMA:
			off_disk = True
			break
		time.sleep(LIMB_SAMPLE_INTERVAL)
	mount.Stop()
	time.sleep(SETTLING_TIME) 

	if not off_disk:
		print("Could not find limb while moving off disk")
		return False
	else:
		print("Moved off disk, now moving back to limb")

	# Get a background level for reference
	background_level = FrameStatistics.standard_deviation
	limb_threshold = max((background_level * LIMB_SIGMA_MULTIPLE), LIMB_SIGMA)

	# Move Westward until we see sigma exceed the limb threshold
	mount.MoveAxis(RA_AXIS, (WESTWARD * LIMB_SEARCH_RATE))
	limb_found = False
	phase_start = time.time()
	while (time.time() - phase_start) < LIMB_SEARCH_TIMEOUT:
		if FrameStatistics.standard_deviation > limb_threshold:
			limb_found = True
			break
		time.sleep(LIMB_SAMPLE_INTERVAL)
	mount.Stop()
	elapsed_time = time.time() - time_0
	if limb_found:
		print ("Limb found in {:.1f} seconds".format(elapsed_time))
	else:
		print("Limb not found")
	time.sleep(SETTLING_TIME) 
	return limb_found

def offset_sun():
	""" Move mount from Sun's East limb to scan start position """
	print("Moving from East limb to scan start position")
	mount.MoveAxis(RA_AXIS, (EASTWARD * OFFSET_RATE))
	time.sleep(offset_time)
	mount.Stop()
	print("At scan start position")
	time.sleep(SETTLING_TIME)
	
def recenter_disk():
	""" Move mount from scan start position to solar disk center """
	print("Moving from scan start position to solar disk center")
	mount.MoveAxis(RA_AXIS, (WESTWARD * RECENTER_RATE))
	time.sleep(recenter_time)
	mount.Stop()
	print("At disk center")
	time.sleep(SETTLING_TIME)

def scan_solar_disk():
	""" Scan the disk from East-side offset to West-side offset """
	FrameStatistics.disable_stats()
	start_image_capture()
	mount.MoveAxis(RA_AXIS, (WESTWARD * scan_rate_actual))
	time.sleep(scan_time)
	mount.Stop()
	camera.StopCapture()
	FrameStatistics.enable_stats()

def run_single_scan(scan_number = 1, SCAN_COUNT = 1, return_to_start = True):
	""" Prepare for the "scan_solar_disk" function.  If the Sun is not on the slit, assume
		the mount is at the scan start position. Otherwise, find the limb and move to the
		East-side offset.
		
		The user is responsible for ensuring the mount is positioned appropriately.
	"""
	print("Start scan {} of {}".format(scan_number, SCAN_COUNT))
	if sun_on_slit():
		find_limb()
		offset_sun()
	print("Scanning solar disk...")
	scan_solar_disk()
	print("Scan captured")
	if return_to_start:
		print("Moving to scan start position")
		move_time = recenter_time * 2.0
	else:
		print("Moving to solar disk center")
		move_time = recenter_time
	mount.MoveAxis(RA_AXIS, (EASTWARD * RECENTER_RATE))
	time.sleep(move_time)
	mount.Stop()
	print("Scan {} of {} complete".format(scan_number, SCAN_COUNT))
	print("")

def run_scan_sequence(return_to_start = True):
	""" Run a complete scan sequence """
	print("Running {} {}".format(SCAN_COUNT, "scans" if SCAN_COUNT > 1 else "scan"))
	for current_scan in range(1, (SCAN_COUNT + 1)):
		run_single_scan(current_scan, SCAN_COUNT, return_to_start)
		if current_scan < SCAN_COUNT:
			print("Waiting {} seconds for next scan".format(SCAN_DELAY))
			time.sleep(SCAN_DELAY)
	print("Scan sequence complete")
	
def scan_from_limb(return_to_start = True):
	"""	The user is responsible for ensuring that the slit is on the Sun's limb,
		either by running "find_limb" or by estimating the limb position by eye.
	"""	
	offset_sun()
	run_single_scan(return_to_start)
	
#-------------------------------------------------------------------------------
#
# Shortcuts for various functions
#
# I've added these to cut down repeated typing. They also let me include simple
# print statements to keep me informed on what's happening. If you put such things
# in a handler for a SharpCap custom button, you won't see the messages until the
# handler has finished running. I'm sure there's a way around that, but this is
# simple, and it works well enough for me.
#
#-------------------------------------------------------------------------------

def fl():
	""" Shortcut for "find_limb" function. """
	find_limb()

def sl():
	""" Shortcut for "scan_from_limb" function. """
	scan_from_limb()

def rs():
	""" Shortcut for "run_scan_sequence" function, returning to start. """
	run_scan_sequence(return_to_start = True)
	
def rc():
	""" Shortcut for "run_scan_sequence" function, returning to center. """
	run_scan_sequence(return_to_start = False)
	
def ss():
	""" Shortcut for "run_single_scan" function, returning to start. """
	run_single_scan()

def sc():
	""" Shortcut for "run_single_scan" function, returning to center. """
	run_single_scan(return_to_start = False)


#-------------------------------------------------------------------------------
#
# Main script section
#
#-------------------------------------------------------------------------------
FrameStatistics = FrameGrabber(camera)
# Shortcut for testing
fs = FrameStatistics
FrameStatistics.attach()
print("SHG-700 scan control version {:.1f}".format(VERSION))
setup_scan()

if not SharpCap.CustomButtons.Find(lambda x : x.Name == "Set Up"):
	setup_icon = Bitmap(SCRIPT_PATH + "\\Icons\\Equipment_Icon.bmp")
	SharpCap.AddCustomButton("Set Up", setup_icon, "Set up SHG scan", setup_scan)

if not SharpCap.CustomButtons.Find(lambda x : x.Name == "Offset"):
	offset_icon = Bitmap(SCRIPT_PATH + "\\Icons\\Offset_Icon.bmp")
	SharpCap.AddCustomButton("Offset", offset_icon, "Move to scan start", offset_sun)

if not SharpCap.CustomButtons.Find(lambda x : x.Name == "Recenter"):
	recenter_icon = Bitmap(SCRIPT_PATH + "\\Icons\\Recenter_Icon.bmp")
	SharpCap.AddCustomButton("Recenter", recenter_icon, "Move to disk center", recenter_disk)
	
if not SharpCap.CustomButtons.Find(lambda x : x.Name == "On Slit"):
	on_slit_icon = Bitmap(SCRIPT_PATH + "\\Icons\\On_Slit_Icon.bmp")
	SharpCap.AddCustomButton("On Slit", on_slit_icon, "Test if on slit", sun_on_slit)
	
	
