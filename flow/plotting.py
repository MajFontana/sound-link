import matplotlib.pyplot
import matplotlib.ticker
import matplotlib.backend_bases
import numpy
import threading
from .nodes import BaseNode
from .dsp import Oscillator, Clock
import time



class PyplotFigure:

    def __init__(self, size):
        matplotlib.backend_bases.NavigationToolbar2.home = self.resetViews

        self.figure, self.axes = matplotlib.pyplot.subplots(size[0], size[1])
        self.plotters = {}

        self.thread = threading.Thread(target=self._threadLoop)
    
    def initialize(self):
        for location, plotter in self.plotters.items():
            axes = self.axes[location[0]][location[1]]
            plotter.initialize(axes)
    
    def resetViews(self):
        for location, plotter in self.plotters.items():
            axes = self.axes[location[0]][location[1]]
            plotter.resetView(axes)

    def addPlotter(self, plotter, location):
        self.plotters[(location[1], location[0])] = plotter

    def update(self):
        for location, plotter in self.plotters.items():
            axes = self.axes[location[0]][location[1]]
            plotter.plot(axes)
        self.figure.canvas.draw_idle()

    def _threadLoop(self):
        while True:
            self.update()
            time.sleep(0.1)
    
    def start(self):
        self.thread.start()



class TimePlotter(BaseNode):

    def __init__(self, sample_rate, window_size, amplitude_range):
        super().__init__()
        self.defineInput("samples")
        self.defineOutput("samples")

        self.clock = Clock(sample_rate, -window_size / sample_rate)
        self.clock.outputs["time"].registerConsumer(self)

        self.sample_rate = sample_rate
        self.window_size = window_size
        self.window = numpy.zeros(window_size)
        self.window_time = self.clock.outputs["time"].read(self.window_size, self)

        self.thread_lock = threading.Lock()

        self.amplitude_range = amplitude_range

    def work(self, sample_count):
        samples = self.inputs["samples"].read(sample_count)
        self.outputs["samples"].write(samples)
        
        time = self.clock.outputs["time"].read(sample_count, self)[-self.window_size:]
        window_time = numpy.concatenate([self.window_time[self.window_size - (self.window_size - len(time)):], time])
        
        samples = samples[-self.window_size:].real        
        window = numpy.concatenate([self.window[self.window_size - (self.window_size - len(samples)):], samples])

        self.thread_lock.acquire()
        self.window_time = window_time
        self.window = window
        self.thread_lock.release()

    def initialize(self, axes):
        self.line = axes.plot([], [])[0]

        x = self.window_time
        y = numpy.zeros(self.window_size)
        self.line.set_data(x, y)

        self.resetView(axes)
    
    def resetView(self, axes):
        x = self.line.get_data()[0]
        axes.set_xlim(x[0], x[-1])
        axes.set_ylim(-self.amplitude_range, self.amplitude_range)

    def plot(self, axes):
        self.thread_lock.acquire()
        x = self.window_time.copy()
        y = self.window.copy()
        self.thread_lock.release()

        prev_t = self.line.get_data()[0]
        xlim = axes.get_xlim()
        tdelta = [xlim[0] - prev_t[0], xlim[1] - prev_t[-1]]
        axes.set_xlim(x[0] + tdelta[0], x[-1] + tdelta[1])

        xlim = axes.get_xlim()
        #xticks = numpy.array(range(math.ceil(x[0] * 100), int(x[-1] * 100) + 1)) / 100
        xticks = numpy.linspace(xlim[0], xlim[1], 5)
        axes.set_xticks(xticks)
        #axes.ticklabel_format(useOffset=False, style="plain")
        axes.xaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter('%.2f'))

        self.line.set_data(x, y)



class FrequencyPlotter(BaseNode):

    def __init__(self, sample_rate, window_size, amplitude_range):
        super().__init__()
        self.defineInputs(["samples"])
        self.defineOutputs(["samples"])

        self.sample_rate = sample_rate
        self.window_size = window_size
        self.window = numpy.zeros(window_size)

        self.amplitude_range = amplitude_range

        self.window_frequency = numpy.fft.fftshift(numpy.fft.fftfreq(self.window_size, d=1 / sample_rate))

        self.thread_lock = threading.Lock()
    
    def initialize(self, axes):
        self.line = axes.plot([], [])[0]

        x = self.window_frequency
        y = numpy.zeros(self.window_size)
        self.line.set_data(x, y)

        self.resetView(axes)
    
    def resetView(self, axes):
        x = self.window_frequency
        axes.set_xlim(x[0], x[-1])
        axes.set_ylim(0, self.amplitude_range)

    def work(self, sample_count):
        samples = self.inputs["samples"].read(sample_count)
        self.outputs["samples"].write(samples)

        samples = samples[-self.window_size:].real
        window = numpy.concatenate([self.window[self.window_size - (self.window_size - len(samples)):], samples])

        self.thread_lock.acquire()
        self.window = window
        self.thread_lock.release()

    def plot(self, axes):
        self.thread_lock.acquire()
        y = self.window.copy()
        self.thread_lock.release()
        f = self.window_frequency
        
        Y = numpy.absolute(numpy.fft.fftshift(numpy.fft.fft(y.real))) / self.window_size * 2
        
        self.line.set_data(f, Y)
        #axes.ticklabel_format(useOffset=False, style="plain")



class IQPlotter(BaseNode):

    def __init__(self, sample_rate, window_size, frequency_offset, amplitude_range):
        super().__init__()
        self.defineInputs(["samples"])
        self.defineOutputs(["samples"])

        self.amplitude_range = amplitude_range

        self.window_size = window_size
        self.window = numpy.zeros(window_size)

        self.oscillator = ManualNode(Oscillator(-frequency_offset, sample_rate))

        self.thread_lock = threading.Lock()
    
    def initialize(self, axes):
        self.scatter = axes.scatter([], [])

        x = numpy.zeros(self.window_size)
        y = numpy.zeros(self.window_size)
        offsets = numpy.array(list(zip(x, y)))
        self.scatter.set_offsets(offsets)

        self.resetView(axes)        
    
    def resetView(self, axes):
        axes.set_xlim(-self.amplitude_range, self.amplitude_range)
        axes.set_ylim(-self.amplitude_range, self.amplitude_range)

    def work(self, sample_count):
        samples = self.inputs["samples"].read(sample_count)
        self.outputs["samples"].write(samples)

        osc = self.oscillator.read(sample_count)
        shifted = samples * osc
        samples = shifted[-self.window_size:]
        window = numpy.concatenate([self.window[self.window_size - (self.window_size - len(samples)):], samples])

        self.thread_lock.acquire()
        self.window = window
        self.thread_lock.release()

    def plot(self, axes):
        self.thread_lock.acquire()
        samps = self.window.copy()
        self.thread_lock.release()
        
        x = samps.real
        y = samps.imag
        
        offsets = numpy.array(list(zip(x, y)))
        self.scatter.set_offsets(offsets)
        #axes.ticklabel_format(useOffset=False, style="plain")
        
