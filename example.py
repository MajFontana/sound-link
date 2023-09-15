from flow.dsp import *
from flow.io import *
from flow.basic import *
from flow.plotting import *
import bitstring
import time
import matplotlib
import threading
import math

SAMP_RATE = 44100
CENTER = 800
DEV = 190
BAUD = 40

audio = AudioIO(2, SAMP_RATE, 1, 1024)

inp = GracefulInputBuffer()
resamp = NearestNeighbourResampler(SAMP_RATE / BAUD)
mod = SineFrequencyModulator(CENTER, DEV, SAMP_RATE, True)

demod = FrequencyDemodulator(CENTER, DEV, 2 * (2 * DEV), 2 * CENTER - 2 * DEV, 2 ** 8, SAMP_RATE)
low = LowPassFilter(BAUD / 2, BAUD / 2, 2 ** 11, SAMP_RATE)
ck = ClockExtractor(BAUD, BAUD * 0.1, 2 ** 13, SAMP_RATE)
ckdel = Delay((2 ** 12) % (SAMP_RATE // BAUD) + (SAMP_RATE // BAUD // 2))
samp = ClockedSampler(1024)
out = OutputBuffer()

#from matplotlib import pyplot
#from scipy import signal
#pyplot.plot(*map(abs, signal.freqz(demod.filter.coefficients, fs=SAMP_RATE)), label="demod")
#pyplot.plot(*map(abs, signal.freqz(low.coefficients, fs=SAMP_RATE)), label="low")
#pyplot.plot(*map(abs, signal.freqz(ck.filter.coefficients, fs=SAMP_RATE)), label="ck")
#pyplot.legend()
#pyplot.show()

fig = PyplotFigure((3, 2))
bas1plot = TimePlotter(SAMP_RATE, 4096, 1.5)
modplot = TimePlotter(SAMP_RATE, 4096, 1.5)
recplot = TimePlotter(SAMP_RATE, 4096, 1.5)
bas2plot = TimePlotter(SAMP_RATE, 4096, 1.5)
lowplot = TimePlotter(SAMP_RATE, 4096, 1.5)
ckplot = TimePlotter(SAMP_RATE, 4096, 1.5)
fig.addPlotter(bas1plot, (0, 0))
fig.addPlotter(modplot, (1, 0))
fig.addPlotter(recplot, (0, 1))
fig.addPlotter(bas2plot, (1, 1))
fig.addPlotter(lowplot, (0, 2))
fig.addPlotter(ckplot, (1, 2))

resamp.inputs["original"].assignProducer(inp.outputs["samples"])
bas1plot.inputs["samples"].assignProducer(resamp.outputs["resampled"])
mod.inputs["baseband"].assignProducer(bas1plot.outputs["samples"])
modplot.inputs["samples"].assignProducer(mod.outputs["modulated"])
audio.inputs["audio_out"][0].assignProducer(modplot.outputs["samples"])

recplot.inputs["samples"].assignProducer(audio.outputs["audio_in"][0])
demod.inputs["modulated"].assignProducer(recplot.outputs["samples"])
bas2plot.inputs["samples"].assignProducer(demod.outputs["baseband"])
low.inputs["original"].assignProducer(bas2plot.outputs["samples"])
lowplot.inputs["samples"].assignProducer(low.outputs["filtered"])
ck.inputs["signal"].assignProducer(lowplot.outputs["samples"])
ckdel.inputs["original"].assignProducer(ck.outputs["clock"])
ckplot.inputs["samples"].assignProducer(ckdel.outputs["delayed"])
samp.inputs["original"].assignProducer(low.outputs["filtered"])
samp.inputs["clock"].assignProducer(ckplot.outputs["samples"])
out.inputs["samples"].assignProducer(samp.outputs["sampled"])

M = b"0.08 kbps :^)"

def producer():
    while True:
        msg = bitstring.Bits(bytes=M)
        preamble = bitstring.Bits(length=16, uint=0x0000)
        sync = bitstring.Bits(length=16, uint=0xC1FA)
        frame = preamble + sync + msg
        man = bitstring.BitArray(length=len(frame) * 2)
        for i, bit in enumerate(frame):
            man[2 * i] = bit
            man[2 * i + 1] = not bit
        samples = numpy.array(man) * 2 - 1
        inp.write(samples)
        time.sleep(((4 + len(M)) * 8 * 2) / BAUD + 0.5)

def consumer():
    sync = bitstring.Bits(length=16, uint=0xC1FA)
    buffer = bitstring.BitArray()
    c = 0
    while True:
        buffer = buffer[-((4 + len(M)) * 8 * 2):]
        sample = out.read(1)[0]
        bit = bitstring.Bits(bool=sample > 0)
        buffer += bit
        deman1 = bitstring.BitArray()
        deman2 = bitstring.BitArray()
        for i in range(len(buffer) // 2):
            if buffer[i * 2] and not buffer[i * 2 + 1]:
                deman1 += bitstring.Bits(bool=True)
            elif not buffer[i * 2] and buffer[i * 2 + 1]:
                deman1 += bitstring.Bits(bool=False)
        for i in range(1, len(buffer) // 2):
            if buffer[i * 2 - 1] and not buffer[i * 2 + 1 - 1]:
                deman2 += bitstring.Bits(bool=True)
            elif not buffer[i * 2 - 1] and buffer[i * 2 + 1 - 1]:
                deman2 += bitstring.Bits(bool=False)
        idx1 = deman1.find(sync)
        idx2 = deman2.find(sync)
        if idx1:
            deman = deman1
            idx = idx1[0]
            trueidx = idx
        elif idx2:
            deman = deman2
            idx = idx2[0]
            trueidx = idx + 1
        else:
            continue
        frame = deman[idx:idx + ((2 + len(M)) * 8)]
        if len(frame) % 8 == 0 and len(frame[16:]) > c:
            try:
                print(frame[-8:].bytes.decode(), end="")
            except:
                print("𖡄", end="")
            c = len(frame[16:])
        #msg = frame[16:].bytes
        #print(msg)
        if len(frame) != (2 + len(M)) * 8:
            continue
        print()
        buffer = buffer[trueidx + ((2 + len(M)) * 8 * 2):]
        c = 0

threading.Thread(target=producer).start()
threading.Thread(target=consumer).start()

fig.initialize()
audio.start()
fig.start()
matplotlib.pyplot.show()

while 1:
    time.sleep(0.1)
