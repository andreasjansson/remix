#!/usr/bin/env python
# encoding: utf=8

"""
capsule.py

accepts songs on the commandline, order them, beatmatch them, and output an audio file

Created by Tristan Jehan and Jason Sundram.
"""

import os
import sys
from optparse import OptionParser
import tempfile
import urllib2

from echonest.action import render, make_stereo
from echonest.audio import LocalAudioFile
from pyechonest import util

from capsule_support import order_tracks, equalize_tracks, resample_features, timbre_whiten, initialize, make_transition, terminate, FADE_OUT, display_actions, is_valid

class Capsule:

    def __init__(self, audio_files, inter, trans, verbose = False, progress_callback = None):
        self.inter = inter
        self.trans = trans
        self.verbose = verbose
        self.progress_callback = progress_callback
        self.tracks = []
        for filename in audio_files:
            try:
                original_filename = None
                if filename is not None and (filename.find('http://') == 0 or filename.find('https://') == 0):
                    _, ext = os.path.splitext(filename)
                    # if unrecognised extension, naively assume mp3
                    if ext not in ['.mp3', '.wav', '.m4a', '.au', '.ogg', '.mp4']:
                        ext = '.mp3'
                    temp_handle, temp_filename = tempfile.mkstemp(ext)
                    if self.verbose:
                        print >> sys.stderr, "Downloading from %s to %s" % (filename, temp_filename)
                    resp = urllib2.urlopen(filename)
                    os.write(temp_handle, resp.read())
                    os.close(temp_handle)
                    original_filename = filename
                    filename = temp_filename

                track = LocalAudioFile(str(filename), verbose=self.verbose, sampleRate = 44100, numChannels = 2)
                if original_filename:
                    track.original_filename = original_filename

                self.tracks.append(track)

                # assume next steps take 10% of the time
                if progress_callback is not None:
                    progress_callback(0.9 * len(self.tracks) / float(len(audio_files)))

            except Exception, e:
                if self.verbose:
                    print >> sys.stderr, 'Failed to analyse %s [%s]' % (filename, e)

    def order(self):
        if self.verbose: print "Ordering tracks..."
        self.tracks = order_tracks(self.tracks)

    def equalize(self):
        equalize_tracks(self.tracks)
        if self.verbose:
            print
            for track in self.tracks:
                print "Vol = %.0f%%\t%s" % (track.gain*100.0, track.analysis.pyechonest_track.id)
            print

    def resample(self):
        valid = []
        # compute resampled and normalized matrices
        for track in self.tracks:
            if self.verbose: print "Resampling features for", track.analysis.pyechonest_track.id
            track.resampled = resample_features(track, rate='beats')
            track.resampled['matrix'] = timbre_whiten(track.resampled['matrix'])
            # remove tracks that are too small
            if is_valid(track, self.inter, self.trans):
                valid.append(track)
            # for compatibility, we make mono tracks stereo
            track = make_stereo(track)
        self.tracks = valid

    def transitions(self):
        # Initial transition. Should contain 2 instructions: fadein, and playback.
        if self.verbose: print "Computing transitions..."
        start = initialize(self.tracks[0], self.inter, self.trans)

        # Middle transitions. Should each contain 2 instructions: crossmatch, playback.
        middle = []
        [middle.extend(make_transition(t1, t2, self.inter, self.trans)) for (t1, t2) in tuples(self.tracks)]

        # Last chunk. Should contain 1 instruction: fadeout.
        end = terminate(self.tracks[-1], FADE_OUT)

        self.actions = start + middle + end

    def render(self, filename):
        if self.verbose:
            print "Rendering..."
        render(self.actions, filename, self.verbose)

    def is_empty(self):
        return len(self.tracks) < 1

    def cleanup(self):
        for track in self.tracks:
            if track.original_filename:
                os.unlink(track.filename)
            track.unload()
        
    

def tuples(l, n=2):
    """ returns n-tuples from l.
        e.g. tuples(range(4), n=2) -> [(0, 1), (1, 2), (2, 3)]
    """
    return zip(*[l[i:] for i in range(n)])

def get_options(warn=False):
    usage = "usage: %s [options] <list of mp3s>" % sys.argv[0]
    parser = OptionParser(usage=usage)
    parser.add_option("-t", "--transition", default=8, help="transition (in seconds) default=8")
    parser.add_option("-i", "--inter", default=8, help="section that's not transitioning (in seconds) default=8")
    parser.add_option("-o", "--order", action="store_true", help="automatically order tracks")
    parser.add_option("-e", "--equalize", action="store_true", help="automatically adjust volumes")
    parser.add_option("-v", "--verbose", action="store_true", help="show results on screen")        
    parser.add_option("-p", "--pdb", default=True, help="dummy; here for not crashing when using nose")
    
    (options, args) = parser.parse_args()
    if warn and len(args) < 2: 
        parser.print_help()
    return (options, args)
    
def main():
    options, args = get_options(warn=True);

    capsule = Capsule(args, float(options.inter), float(options.transition), options.verbose)

    # decide on an initial order for those tracks
    if options.order == True:
        capsule.order()
    
    if options.equalize == True:
        capsule.equalize()

    capsule.resample()
    
    if capsule.is_empty(): return []

    capsule.transitions()

    # Send to renderer
    capsule.render('capsule.mp3')
    return 1
    
if __name__ == "__main__":
    main()
    # for profiling, do this:
    #import cProfile
    #cProfile.run('main()', 'capsule_prof')
    # then in ipython:
    #import pstats
    #p = pstats.Stats('capsule_prof')
    #p.sort_stats('cumulative').print_stats(30)

