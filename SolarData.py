# -------------------------------------------------------------------------------
#
#	Solar coordinates calculations, to an accuracy of about 1 arc-minute,
#	adapted from USNO Note "Computing Approximate Solar Coordinates (Retrieved 2026 March 03)
#
#	Julian day calculation adapted from the book Astronomical Algorithms, 2nd edition,
#	by Jean Meeus 
#
# -------------------------------------------------------------------------------
#
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

	# Consistent symbols
	#------------------------
	# D: days since epoch
	# g: mean anomaly of Sun
	# q: mean longitude Sun
	
from math import radians, sin, cos
import datetime

def ymd_date(full_date):
	# Get date in modified ymd format, with the day including a fraction computed from time
	# In standard Python, generate full_date with "datetime.datetime.now(datetime.UTC)"
	# In IronPython, use datetime.datetime.utcnow()

	y = full_date.year
	m = full_date.month
	d = full_date.day + (full_date.hour + (full_date.minute + full_date.second/60)/60)/24
	return (y, m, d)

def julian_day(ymd):
	y = ymd[0]
	m = ymd[1]
	d = ymd[2]

	# From Astronomical Algorithms, 2nd. ed. p.61
	if m > 2:
		m_adjusted = m
		y_adjusted = y
	else:
		m_adjusted = m + 12
		y_adjusted = y - 1
	a = int(y_adjusted / 100)
	b = 2 - a + int(a / 4)
	jd = int(365.25 * (y_adjusted + 4716)) + int(30.6001 * (m_adjusted + 1)) + d + b - 1524.5
	return jd

def days_from_j2000 (jd):
	return jd - 2451545.0
	
def mean_anomaly(D):
	return (357.529 + 0.98560028 * D) % 360.0

def mean_longitude(D):
	return (280.459 + 0.98564736 * D) % 360.0
	
def apparent_longitude(D, g, q):
	return q + 1.915 * sin(radians(g)) + 0.020 * sin(radians(2 * g))
	
def r_earth_sun(g):
	# Earth-Sun distance in AU
	return 1.00014 - 0.01671 * cos(radians(g)) - 0.00014 * sin(radians(2 * g))
	
def sun_diameter(jd):
	D = days_from_j2000(jd)
	g = mean_anomaly(D)
	rES = r_earth_sun(g)
	diameter = 2 * (0.2666 / rES) * 3600
	# Sun's apparent diameter in arc-sec
	return diameter
	
def get_sun_diameter():
	""" Sun's diameter in arc-sec for today's date in UTC """
	full_date = datetime.datetime.utcnow()
	ymd = ymd_date(full_date)
	jd = julian_day(ymd)
	return sun_diameter(jd)	
