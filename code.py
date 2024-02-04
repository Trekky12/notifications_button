import time
import board
import neopixel
from rainbowio import colorwheel
import digitalio
from adafruit_debouncer import Debouncer

import os
import socketpool
import wifi

from adafruit_httpserver import Server, Request, Response

import traceback

import json

COLOR_PURPLE = (180, 0, 255)
COLOR_DISABLED = (0,0,0)

switch_pin = digitalio.DigitalInOut(board.IO3)
switch_pin.direction = digitalio.Direction.INPUT
switch_pin.pull = digitalio.Pull.UP
switch = Debouncer(switch_pin, interval=0.02)

pixels_pwr = digitalio.DigitalInOut(board.IO5)
pixels_pwr.direction = digitalio.Direction.OUTPUT
pixels_pwr.value = True

num_pixels = 13

pixels = neopixel.NeoPixel(board.IO4, num_pixels, brightness=0.1, auto_write=False)
pixels.fill(COLOR_DISABLED)
pixels.show()

motor = digitalio.DigitalInOut(board.IO1)
motor.direction = digitalio.Direction.OUTPUT

lightAnimationStartTime = 0
lightAnimationColorIndex = 0
lightAnimationPixelIndex = 0

# 10ms
lightAnimationInterval = 1000*1000*1000*0.01
lightAnimationInterval = 0

# Use static light or rainbow cycle
isStaticLight = True

# Light is enabled  => Light should be active
isLightEnabled = False
# Actual state of the light => is set one when when isLightEnabled changes
isLightOn = False

config = {'color': {'r': 255, 'g': 0, 'b': 0}}

pool = socketpool.SocketPool(wifi.radio)

server = Server(pool, debug=True)

@server.route("/control/<action>", append_slash=True)
def control(request: Request, action: str):
    global isLightEnabled, config, isLightOn
    if action == "light_on":
        isLightEnabled = True
    elif action == "light_off":
        isLightEnabled = False
        disableLight()
    elif action == "color":
        r = request.query_params.get("r") or 0
        g = request.query_params.get("g") or 0
        b = request.query_params.get("b") or 0
        config['color']['r'] = int(r)
        config['color']['g'] = int(g)
        config['color']['b'] = int(b)
        writeConfig()
        if isLightOn:
            pixels.fill((config['color']['r'], config['color']['g'], config['color']['b']))
            pixels.show()
    else:
        return Response(request, f"Unknown action ({action})")

    return Response(
        request, f"Action ({action}) performed"
    )


# Classic rainbow cycle with delay
# Each LED fades through all colors while each LED has the "next" color
def rainbow_cycle_delay():
    global lightAnimationPixelIndex, lightAnimationColorIndex, lightAnimationStartTime

    for j in range(255):
        for i in range(num_pixels):
            rc_index = (i * 256 // num_pixels) + j
            color = colorwheel(rc_index & 255)
            pixels[i] = color
        pixels.show()
        time.sleep(0.1)

# Classic rainbow cycle without delay
# Each LED fades through all colors while each LED has the "next" color
def rainbow_cycle():
    global lightAnimationPixelIndex, lightAnimationColorIndex, lightAnimationStartTime

    for i in range(num_pixels):
        rc_index = (i * 256 // num_pixels) + lightAnimationColorIndex * 4
        color = colorwheel(rc_index & 255)
        pixels[i] = color
    pixels.show()

    lightAnimationColorIndex = lightAnimationColorIndex + 1
    if lightAnimationColorIndex > 255:
        lightAnimationColorIndex = 0

    lightAnimationPixelIndex = lightAnimationPixelIndex + 1
    if lightAnimationPixelIndex == num_pixels:
        lightAnimationPixelIndex = 0

# Only one LED at the time is on
# Afterwards the next led is on
# After all LEDs were on the next color is used
def rainbow_cycle1():
    global lightAnimationPixelIndex, lightAnimationColorIndex, lightAnimationStartTime

    for i in range(num_pixels):
        if i == lightAnimationPixelIndex:
            rc_index = (256 // num_pixels) + lightAnimationColorIndex
            color = colorwheel(rc_index & 255)
            pixels[i] = color
        else:
            pixels[i] = COLOR_DISABLED
    pixels.show()

    lightAnimationColorIndex = lightAnimationColorIndex + 1
    if lightAnimationColorIndex > 255:
        lightAnimationColorIndex = 0

    lightAnimationPixelIndex = lightAnimationPixelIndex + 1
    if lightAnimationPixelIndex == num_pixels:
        lightAnimationPixelIndex = 0


# All LEDs fading through all colors at the same time
def rainbow_cycle2():
    global lightAnimationPixelIndex, lightAnimationColorIndex, lightAnimationStartTime

    for i in range(num_pixels):
        rc_index = (256 // num_pixels) + lightAnimationColorIndex
        color = colorwheel(rc_index & 255)
        pixels[i] = color
    pixels.show()

    lightAnimationColorIndex = lightAnimationColorIndex + 1
    if lightAnimationColorIndex > 255:
        lightAnimationColorIndex = 0

    lightAnimationPixelIndex = lightAnimationPixelIndex + 1
    if lightAnimationPixelIndex == num_pixels:
        lightAnimationPixelIndex = 0


def disableLight():
    global isLightOn
    isLightOn = False
    pixels.fill(COLOR_DISABLED)
    pixels.show()


def connectToWifi():
    global pool
    while not wifi.radio.connected:
        print("Connecting to Wifi")
        try:
            wifi.radio.connect(os.getenv("WIFI_SSID"), os.getenv("WIFI_PASSWORD"))
            pool = socketpool.SocketPool(wifi.radio)
        except Exception as error:
            print("Connect failed, retrying in 1 min...\n", error)
            #traceback.print_exception(None, error, error.__traceback__, limit=-1)
            time.sleep(60)
            continue

    server.start(str(wifi.radio.ipv4_address))

def writeLog(message):
    try:
        with open("/logfile.txt", "a") as fp:
            if isinstance(message, Exception):
                traceback.print_exception(None, message, message.__traceback__, -1, fp)
            else:
                fp.write('{}\n'.format(message))
                fp.flush()
    except OSError as e:  # Typically when the filesystem isn't writeable...
        print("Error when writing file")
        pass

def writeConfig():
    global config
    try:
        with open("/config.json", "w") as fp:
            json.dump(config, fp)
    except OSError as e:
        print("Error when writing file")
        pass

def readConfig():
    global config
    try:
        with open("/config.json", "r") as fp:
            config = json.load(fp)
    except OSError as e:
        print("Error when reading file")
        pass

try:
    if not 'config.json' in os.listdir():
        writeConfig()
    readConfig()
    print(config)
    writeLog("Hello from Notifications Button")
    connectToWifi()
    while True:
        # Button Press
        switch.update()
        if switch.fell:
            print("button pressed")

            # enable/disable light
            if not isLightEnabled:
                isLightEnabled = True
            else:
                disableLight()
                isLightEnabled = False
                isLightOn = False

        # Enable light if enabled and not on
        if isLightEnabled and not isLightOn:
            isLightOn = True

            motor.value = True
            time.sleep(1)
            motor.value = False

            if isStaticLight:
                pixels.fill((config['color']['r'],config['color']['g'],config['color']['b']))
                pixels.show()
            #rainbow_cycle_delay()

            lightAnimationPixelIndex = 0
            lightAnimationColorIndex = 0
            lightAnimationStartTime = 0

        # Trigger animation step if light is on every 10ms
        if not isStaticLight and isLightOn and (lightAnimationStartTime + lightAnimationInterval < time.monotonic_ns()):
            rainbow_cycle()
            #rainbow_cycle1()
            #rainbow_cycle2()
            lightAnimationStartTime = time.monotonic_ns()

        if wifi.radio.enabled:
            server.poll()

except Exception as e:
    print(e)
    writeLog("There was an error")
    writeLog(e)
    pixels.fill(COLOR_PURPLE)
    pixels.show()
