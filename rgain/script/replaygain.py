# -*- coding: utf-8 -*-
# 
# Copyright (c) 2009 Felix Krull <f_krull@gmx.de>
# 
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.

import sys
import os.path

import gobject

from rgain import rgio
from rgain.script import ou, un, Error, common_options


# calculate the gain for the given files
def calculate_gain(files, ref_level):
    # this has to be done here since Gstreamer hooks into the command line
    # arguments if it's imported on module level
    from rgain import rgcalc
    
    # handlers
    def on_finished(src):
        loop.quit()
    
    def on_trk_started(src, filename):
        print ou("  %s:" % filename),
        sys.stdout.flush()
        
    def on_trk_finished(src, filename):
        gaindata = rg.track_data.get(filename)
        if gaindata:
            print "%.2f dB" % gaindata.gain
        else:
            print "done"
    
    rg = rgcalc.ReplayGain(files, True, ref_level)
    rg.connect("all-finished", on_finished)
    rg.connect("track-started", on_trk_started)
    rg.connect("track-finished", on_trk_finished)
    loop = gobject.MainLoop()
    rg.start()
    loop.run()
    return rg.track_data, rg.album_data


def do_gain(files, ref_level=89, force=False, dry_run=False, album=True,
            mp3_format="ql"):
    
    files = [un(filename, sys.getfilesystemencoding()) for filename in files]
    
    formats_map = rgio.BaseFormatsMap(mp3_format)
    
    newfiles = []
    for filename in files:
        if not os.path.splitext(filename)[1] in formats_map.supported_formats:
            print ou(u"%s: not supported, ignoring it" % filename)
        else:
            newfiles.append(filename)
    files = newfiles
    
    if not force:
        print "Checking for Replay Gain information ..."
        newfiles = []
        for filename in files:
            print ou(u"  %s:" % filename),
            try:
                trackdata, albumdata = formats_map.read_gain(filename)
            except Exception, exc:
                raise Error(u"%s: error - %s" % (filename, exc))
            else:
                if trackdata and albumdata:
                    print "track and album"
                elif not trackdata and albumdata:
                    print "album only"
                    newfiles.append(filename)
                elif trackdata and not albumdata:
                    print "track only"
                    if album:
                        newfiles.append(filename)
                else:
                    print "none"
                    newfiles.append(filename)
        
        if not album:
            files = newfiles
        elif not len(newfiles):
            files = newfiles
    
    if not files:
        # no files left
        print "Nothing to do."
        return 0
    
    # calculate gain
    print "Calculating Replay Gain information ..."
    try:
        tracks_data, albumdata = calculate_gain(files, ref_level)
        if album:
            print "  Album gain: %.2f dB" % albumdata.gain
    except Exception, exc:
        raise Error(u"Error while calculating gain - %s" % exc)
    
    if not album:
        albumdata = None
    
    # write gain
    if not dry_run:
        print "Writing Replay Gain information to files ..."
        for filename, trackdata in tracks_data.iteritems():
            print ou(u"  %s:" % filename),
            try:
                formats_map.write_gain(filename, trackdata, albumdata)
            except Exception, exc:
                raise Error(u"%s: error - %s" % (filename, exc))
            else:
                print "done"
    
    print "Done"


# a simple Replay Gain dump
def show_rgain_info(filenames, mp3_format="ql"):
    formats_map = rgio.BaseFormatsMap(mp3_format)
    
    for filename in filenames:
        filename = un(filename, sys.getfilesystemencoding())
        print ou(filename)
        try:
            trackdata, albumdata = formats_map.read_gain(filename)
        except Exception, exc:
            print "  <Error reading Replay Gain: %r>" % exc
            continue
        
        if not trackdata and not albumdata:
            print "  <No Replay Gain information>"
        
        if trackdata and trackdata.ref_level:
            ref_level = trackdata.ref_level
        elif albumdata and albumdata.ref_level:
            ref_level = albumdata.ref_level
        else:
            ref_level = None
        
        if ref_level is not None:
            print "  Reference loudness %i dB" % ref_level
        
        if trackdata:
            print "  Track gain %.2f dB" % trackdata.gain
            print "  Track peak %.8f" % trackdata.peak
        if albumdata:
            print "  Album gain %.2f dB" % albumdata.gain
            print "  Album peak %.8f" % albumdata.peak


def rgain_options():
    opts = common_options()
    
    opts.add_option("--no-album", help="Don't write any album gain "
                    "information.", dest="album", action="store_false")
    opts.add_option("--show", help="Don't calculate anything, simply show "
                    "Replay Gain information for the specified files. In this "
                    "mode, all other options save for '--mp3-format' are "
                    "ignored, for they would make no sense.", dest="show",
                    action="store_true")
    
    opts.set_defaults(album=True, show=False)
    
    opts.set_usage("%prog [options] AUDIO_FILE [AUDIO_FILE ...]")
    opts.set_description("Apply or display Replay Gain information for audio "
                         "files. This program is similar to the likes of "
                         "'vorbisgain' or 'mp3gain': You pass in some files, "
                         "they are analyzed and receive their share of Replay "
                         "Gain. The difference is that '%prog' supports "
                         "several file formats, namely Ogg Vorbis (anything "
                         "you'd put into an Ogg container, actually), Flac, "
                         "WavPack and MP3. Also, it allows you to view "
                         "existing Replay Gain information in any of those "
                         "file types.")
    
    return opts


def rgain():
    optparser = rgain_options()
    opts, args = optparser.parse_args()
    if not args:
        optparser.error("pass one or several audio file names")
    
    if opts.show:
        show_rgain_info(args, opts.mp3_format)
    else:
        try:
            do_gain(args, opts.ref_level, opts.force, opts.dry_run, opts.album,
                    opts.mp3_format)
        except Error, exc:
            print >> sys.stderr, ou(unicode(exc))
            sys.exit(1)
        except KeyboardInterrupt:
            print "Interrupted."


if __name__ == "__main__":
    rgain()
