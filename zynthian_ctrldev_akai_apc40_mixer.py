#!/usr/bin/python3
# -*- coding: utf-8 -*-
#******************************************************************************
# ZYNTHIAN PROJECT: Zynthian Control Device Driver
#
# Zynthian Control Device Driver for "Akai MIDI-mix"
#
# Copyright (C) 2015-2023 Fernando Moyano <jofemodo@zynthian.org>
#                         Brian Walton <brian@riban.co.uk>
#
#******************************************************************************
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of
# the License, or any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# For a full copy of the GNU General Public License see the LICENSE.txt file.
#
#******************************************************************************

import logging
import sys
# Zynthian specific modules
from zyngui import zynthian_gui_config
from zyngui.zynthian_ctrldev_manager import zynthian_ctrldev_zynpad
from zyncoder.zyncore import lib_zyncore
from zynlibs.zynseq import zynseq

# --------------------------------------------------------------------------
# Akai MIDI-Mix Integration
# --------------------------------------------------------------------------

# All the launch button colour states
COLOUR_OFF = 0
COLOUR_GREEN = 1
COLOUR_GREEN_BLINK = 2
COLOUR_RED = 3
COLOUR_RED_BLINK = 4
COLOUR_ORANGE = 5
COLOUR_ORANGE_BLINK = 6
# Byte sequence to set the mode.
CTRL_MODE_REQ = "F0 47 00 73 60 00 04 42 00 00 00 F7"
# Launch grid notes all fall between these values, which determine
# the y coordinates of button presses on the grid.
PAD_NOTE_MIN = 0x35
PAD_NOTE_MAX = 0x39

PAD_WIDTH = 8
PAD_HEIGHT = 5

class zynthian_ctrldev_akai_apc40_mixer(zynthian_ctrldev_zynpad):

	dev_ids = ["Akai_APC40_MIDI_1"]
	dev_zynmixer = True  # Can act as an audio mixer controller device
	rec_mode = 0
	bank_left_note = 89 # Send B
	bank_right_note = 90 # Send C
	mute_note = 50
	solo_note = 49
	rec_note = 51
	panknobs_ccnum = [48, 49, 50, 51, 52, 53, 54, 55]
	ccknobs_ccnum = [16, 17, 18, 19, 20, 21, 22, 23]
	fader_ccnum = 7
	master_select_nnum = 80
	master_chnum = 0
	master_ccnum = 14
	pan_selected = True
	pan_button = 87

	# Function to initialise class
	def __init__(self):
		super().__init__()
		self.midimix_bank = 0
		self.zynmixer = self.zyngui.zynmixer
		self.zyngui_mixer = self.zyngui.screens["audio_mixer"]
		self.zynpad = self.zyngui.screens["zynpad"]

	def setup_sysex(self):
		msg = bytes.fromhex(CTRL_MODE_REQ)
		lib_zyncore.dev_send_midi_event(self.idev, msg, len(msg))
		
	def setup_pan_led_rings(self):
		for cc in self.panknobs_ccnum:
			lib_zyncore.dev_send_ccontrol_change(self.idev, 0, cc + 8, 3)
	
	def setup_cc_led_rings(self):
		for cc in self.ccknobs_ccnum:
			lib_zyncore.dev_send_ccontrol_change(self.idev, 0, cc + 8, 2)

	def init(self):
		self.midimix_bank = 0
		self.light_off()
		self.setup_sysex()
		self.setup_pan_led_rings()
		self.setup_cc_led_rings()

	def end(self):
		self.light_off()
	
	def convert_range(self, value, old_min, old_max, new_min, new_max):
		old_range = old_max - old_min
		new_range = new_max - new_min
		new_value = (((value - old_min) * new_range) / old_range) + new_min
		return int(new_value)

	# Update LED status
	def refresh(self, force = False):
		# Setup Pan
		if self.pan_selected:
			lib_zyncore.dev_send_note_on(self.idev, 0, self.pan_button, 1)
   
		# Bank selection LED
		if self.midimix_bank:
			index0 = 8
			lib_zyncore.dev_send_note_on(self.idev, 0, self.bank_left_note, 0)
			lib_zyncore.dev_send_note_on(self.idev, 0, self.bank_right_note, 1)
		else:
			index0 = 0
			lib_zyncore.dev_send_note_on(self.idev, 0, self.bank_left_note, 1)
			lib_zyncore.dev_send_note_on(self.idev, 0, self.bank_right_note, 0)

		# Strips Leds
		layers = self.zyngui.screens['layer'].get_root_layers()
		for i in range(0, 8):
			index = index0 + i
			if index < len(self.zyngui.zynmixer.zctrls):
				mute = self.zyngui.zynmixer.get_mute(index)
				solo = self.zyngui.zynmixer.get_solo(index)
				panPosition = self.convert_range(self.zyngui.zynmixer.get_balance(index), -1, 1, 0, 127)
			else:
				mute = 0
				solo = 0

			if not self.rec_mode:
				if index < len(layers) and self.zyngui.curlayer and layers[index] == self.zyngui.curlayer:
					rec = 1
				else:
					rec = 0
			else:
				if index < len(layers) - 1:
					rec = self.zyngui.audio_recorder.is_armed(layers[index].midi_chan)
				else:
					rec = 0

			lib_zyncore.dev_send_note_on(self.idev, index, self.mute_note, mute)
			lib_zyncore.dev_send_note_on(self.idev, index, self.solo_note, solo)
			lib_zyncore.dev_send_note_on(self.idev, index, self.rec_note, rec)
			lib_zyncore.dev_send_ccontrol_change(self.idev, 0, self.panknobs_ccnum[index % 8], panPosition)

	def decode_channel(self, event):
        # The APC40 launch grid splits its columns along MIDI channels 0 - 7,
        # so we need to know which channel an event was sent on to determine
        # the x coordinate of the button that was pressed
		status_byte = (event >> 16) & 0xFF
		channel = (status_byte & 0x0F)
		return channel
    
	def midi_event(self, ev):
		evtype = (ev & 0xF00000) >> 20
		idev = (ev & 0xFF000000) >> 24
		channel = self.decode_channel(ev)
		note = None
		if evtype == 0x9:
			note = (ev >> 8) & 0x7F
			val = ev & 0x7F
			if note == self.bank_left_note:
				self.midimix_bank = 0
				self.refresh()
				return True
			elif note == self.bank_right_note:
				self.midimix_bank = 1
				self.refresh()
				return True
			elif note == self.mute_note:
				index = channel
				if self.midimix_bank:
					index += 8
				if self.zynmixer.get_mute(index):
					val = 0
				else:
					val = 1
				self.zynmixer.set_mute(index, val, True)
				# Send LED feedback
				lib_zyncore.dev_send_note_on(self.idev, channel, note, val)
				return True
			elif note == self.solo_note:
				index = channel
				if self.midimix_bank:
					index += 8
				if self.zynmixer.get_solo(index):
					val = 0
				else:
					val = 1
				self.zynmixer.set_solo(index, val, True)
				# Update Main "solo" control
				self.zyngui_mixer.pending_refresh_queue.add((self.zyngui_mixer.main_mixbus_strip, 'solo'))
				# Send LED feedback
				lib_zyncore.dev_send_note_on(self.idev, channel, note, val)
				return True
			elif note == self.rec_note:
				index = channel
				if self.midimix_bank:
					index += 8
				if index < len(self.zynmixer.zctrls) - 1:
					if not self.rec_mode:
						self.zyngui_mixer.select_chain_by_index(index)
					else:
						layer = self.zyngui.screens['layer'].get_root_layers()[index]
						self.zyngui.audio_recorder.toggle_arm(layer.midi_chan)
						# Send LED feedback
						val = self.zyngui.audio_recorder.is_armed(layer.midi_chan)
						lib_zyncore.dev_send_note_on(self.idev, channel, note, val)
				return True
			# launch pad button press
			elif (note and channel >= 0 and channel <= 7):
				x = channel
				y = note - PAD_NOTE_MIN
				if y < PAD_HEIGHT and y > -1:
					pad = self.zynpad.get_pad_from_xy(x, y)
					if pad >= 0:
						self.zyngui.zynseq.libseq.togglePlayState(self.zynpad.bank, pad)
					return True
		elif evtype == 0xB:
			ccnum = (ev & 0x7F00) >> 8
			ccval = (ev & 0x007F)
			if channel == self.master_chnum and ccnum == self.master_ccnum:
				self.zyngui_mixer.main_mixbus_strip.zctrls['level'].set_value(ccval/127.0)
				return True
			elif ccnum == self.fader_ccnum:
				index = channel
				if self.midimix_bank:
					index += 8
				self.zynmixer.set_level(index, ccval/127.0, True)
				return True
			elif ccnum in self.panknobs_ccnum:
				index = self.panknobs_ccnum.index(ccnum)
				if self.midimix_bank:
					index += 8
				self.zynmixer.set_balance(index, 2.0 * ccval/127.0 - 1.0)
				return True
			else:
				lib_zyncore.dev_send_ccontrol_change(self.idev, channel, ccnum, ccval)

	# Light-Off all LEDs
	def light_off(self):
		for note in range(0, 128):
			for channel in range(8):
				lib_zyncore.dev_send_note_on(self.idev, channel, note, 0)

	    # It *SHOULD* be implemented by child class
	def refresh_zynpad_bank(self):
        # TODO: implement this
		pass

	def update_pad(self, pad, state, mode):
		logging.debug("Updating APC40 pad {}".format(pad))
		col, row = self.zynpad.get_xy_from_pad(pad)
		if (col >= PAD_WIDTH or row >= PAD_HEIGHT):
			logging.debug(f"Pad position {col}{row} out of bounds for APC40")
			return False

		channel = col
		note = PAD_NOTE_MIN + row
		group = self.zyngui.zynseq.libseq.getGroup(self.zynpad.bank, pad)

        # The velocity value in messages sent to the pad is used to set button colour state
		try:
			if mode == 0:
				velocity = COLOUR_RED
			elif state == zynseq.SEQ_STOPPED:
				velocity = COLOUR_RED
			elif state == zynseq.SEQ_PLAYING:
				velocity = COLOUR_GREEN
			elif state == zynseq.SEQ_STOPPING:
				velocity = COLOUR_ORANGE
			elif state == zynseq.SEQ_STARTING:
				velocity = COLOUR_GREEN_BLINK
			else:
				velocity = COLOUR_RED
		except:
			velocity = COLOUR_RED

		logging.debug("Lighting PAD {}, group {} => {}, {}, {}".format(pad, group, channel, note, velocity))
		lib_zyncore.dev_send_note_on(self.idev, channel, note, velocity)

#------------------------------------------------------------------------------

