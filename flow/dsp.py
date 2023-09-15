import numpy
import scipy.signal
import math
from .nodes import Buffer, BaseNode
from .basic import Clock



class Oscillator(BaseNode):

    def __init__(self, frequency, sample_rate):
        super().__init__()
        
        self.defineOutput("sine")

        self.clock = Clock(sample_rate)
        self.clock.outputs["time"].registerConsumer(self)

        self.frequency = frequency

    def work(self, sample_count):
        time_points = self.clock.outputs["time"].read(sample_count, self)
        oscillator_i = numpy.cos(time_points * 2 * numpy.pi * self.frequency)
        oscillator_q = numpy.sin(time_points * 2 * numpy.pi * self.frequency)
        oscillator = oscillator_i + 1j * oscillator_q
        self.outputs["sine"].write(oscillator)



class RandomSymbolSource(BaseNode):

    def __init__(self, symbol_count):
        super().__init__()
        self.defineOutput("symbols")

        self.symbol_count = symbol_count

    def work(self, sample_count):
        randint = numpy.random.randint(0, self.symbol_count, sample_count)
        normalized = 2 * randint / (self.symbol_count - 1) - 1
        self.outputs["symbols"].write(normalized)



class VariableFrequencyOscillator(BaseNode):

    def __init__(self, sample_rate, continuous_phase):
        super().__init__()
        self.defineInput("frequency")
        self.defineOutput("sine")

        self.continuous_phase = continuous_phase
        self.last_phase = 0
        self.last_time = 0
        
        self.clock = Clock(sample_rate)
        self.clock.outputs["time"].registerConsumer(self)

    def work(self, sample_count):
        frequency = self.inputs["frequency"].read(sample_count)
        time_points = self.clock.outputs["time"].read(sample_count, self)
        if self.continuous_phase:
            time_deltas = numpy.diff(numpy.insert(time_points, 0, self.last_time))
            self.last_time = time_points[-1]
            phase_deltas = time_deltas * 2 * numpy.pi * frequency
            phase = numpy.cumsum(phase_deltas) + self.last_phase
            self.last_phase = phase[-1]
        else:
            phase = time_points * 2 * numpy.pi * frequency
        oscillator_i = numpy.cos(phase)
        oscillator_q = numpy.sin(phase)
        oscillator = oscillator_i + 1j * oscillator_q
        self.outputs["sine"].write(oscillator)



class SineFrequencyModulator(BaseNode):

    def __init__(self, center_frequency, deviation, sample_rate, continuous_phase):
        super().__init__()
        self.defineInput("baseband")
        self.defineOutput("modulated")

        self.center_frequency = center_frequency
        self.deviation = deviation

        self.oscillator = VariableFrequencyOscillator(sample_rate, continuous_phase)
        self.oscillator.outputs["sine"].registerConsumer(self)

    def work(self, sample_count):
        baseband = self.inputs["baseband"].read(sample_count)
        frequency = baseband * self.deviation + self.center_frequency
        self.oscillator.inputs["frequency"].write(frequency)
        modulated = self.oscillator.outputs["sine"].read(sample_count, self)
        self.outputs["modulated"].write(modulated)



class FrequencyDemodulator(BaseNode):

    def __init__(self, center_frequency, deviation, band_width, margin, node_count, sample_rate):
        super().__init__()
        self.defineInput("modulated")
        self.defineOutput("baseband")

        self.deviation = deviation
        self.sample_rate = sample_rate

        self.shifter = FrequencyShifter(-center_frequency, sample_rate)

        self.filter = LowPassFilter(band_width / 2, margin, node_count, sample_rate)
        self.filter.inputs["original"].assignProducer(self.shifter.outputs["shifted"])
        self.filter.outputs["filtered"].registerConsumer(self)

        self.delay = Delay(1)
        self.delay.inputs["original"].assignProducer(self.filter.outputs["filtered"])
        self.delay.outputs["delayed"].registerConsumer(self)

    def work(self, sample_count):
        modulated = self.inputs["modulated"].read(sample_count)
        self.shifter.inputs["original"].write(modulated)
        filtered = self.filter.outputs["filtered"].read(sample_count, self)
        delayed = self.delay.outputs["delayed"].read(sample_count, self)
        angular_velocity = -numpy.angle(filtered * delayed.conjugate())
        frequency = angular_velocity / numpy.pi * self.sample_rate / 2
        baseband = frequency / self.deviation
        self.outputs["baseband"].write(baseband)



class Delay(BaseNode):

    def __init__(self, amount):
        super().__init__()
        self.defineInput("original")
        self.defineOutput("delayed")
        
        self.buffer = Buffer()
        self.buffer.write(numpy.zeros(amount))

    def work(self, sample_count):
        original = self.inputs["original"].read(sample_count)
        self.buffer.write(original)
        delayed = self.buffer.read(sample_count)
        self.outputs["delayed"].write(delayed)



class FrequencyShifter(BaseNode):

    def __init__(self, shift_amount, sample_rate):
        super().__init__()
        self.defineInput("original")
        self.defineOutput("shifted")
        
        self.oscillator = Oscillator(-shift_amount, sample_rate)
        self.oscillator.outputs["sine"].registerConsumer(self)

    def work(self, sample_count):
        oscillator = self.oscillator.outputs["sine"].read(sample_count, self)
        original = self.inputs["original"].read(sample_count)
        shifted = oscillator * original
        self.outputs["shifted"].write(shifted)



class AmplitudeModulator(BaseNode):

    def __init__(self):
        super().__init__()
        self.defineInput("signal 1")
        self.defineInput("signal 2")
        self.defineOutput("modulated")

    def work(self, sample_count):
        signal1 = self.inputs["signal 1"].read(sample_count)
        signal2 = self.inputs["signal 2"].read(sample_count)
        modulated = signal1 * signal2
        self.outputs["modulated"].write(modulated)



class ManchesterCoder(BaseNode):

    def __init__(self, low_to_high_zero):
        super().__init__()
        self.defineInput("decoded")
        self.defineOutput("encoded")

        self.low_to_high_zero = low_to_high_zero

    def work(self, sample_count):
        input_amount = math.ceil(sample_count / 2)
        samples = self.inputs["decoded"].read(input_amount)
        encoded = numpy.empty(input_amount * 2)
        if self.low_to_high_zero:
            encoded[0::2] = -samples
            encoded[1::2] = samples
        else:
            encoded[0::2] = samples
            encoded[1::2] = -samples
        self.outputs["encoded"].write(encoded)



class LowPassFilter(BaseNode):

    def __init__(self, cutoff_frequency, transition_width, node_count, sample_rate):
        super().__init__()
        self.defineInput("original")
        self.defineOutput("filtered")
        
        frequencies = [0, cutoff_frequency, cutoff_frequency + transition_width, sample_rate / 2]
        gain = [1, 1, 0, 0]
        self.coefficients = scipy.signal.firwin2(node_count, frequencies, gain, fs=sample_rate)
        self.filter_state = numpy.zeros(node_count - 1)

    def work(self, sample_count):
        signal = self.inputs["original"].read(sample_count)
        filtered, self.filter_state = scipy.signal.lfilter(self.coefficients, 1, signal, zi=self.filter_state)
        self.outputs["filtered"].write(filtered)



class Filter(BaseNode):

    def __init__(self, frequencies, gain, node_count, sample_rate):
        super().__init__()
        self.defineInput("unfiltered")
        self.defineOutput("filtered")
        
        self.coefficients = scipy.signal.firwin2(node_count, frequencies, gain, fs=sample_rate)
        self.filter_state = numpy.zeros(node_count - 1)

    def work(self, sample_count):
        unfiltered = self.inputs["unfiltered"].read(sample_count)
        filtered, self.filter_state = scipy.signal.lfilter(self.coefficients, 1, unfiltered, zi=self.filter_state)
        self.outputs["filtered"].write(filtered)



class BandpassFilter(BaseNode):

    def __init__(self, low_cutoff_frequency, high_cutoff_frequency, transition_width, node_count, sample_rate):
        super().__init__()
        self.defineInput("unfiltered")
        self.defineOutput("filtered")
        
        frequencies = [0, low_cutoff_frequency - transition_width, low_cutoff_frequency, high_cutoff_frequency, high_cutoff_frequency + transition_width, sample_rate / 2]
        gain = [0, 0, 1, 1, 0, 0]
        self.coefficients = scipy.signal.firwin2(node_count, frequencies, gain, fs=sample_rate)
        self.filter_state = numpy.zeros(node_count - 1)

    def work(self, sample_count):
        unfiltered = self.inputs["unfiltered"].read(sample_count)
        filtered, self.filter_state = scipy.signal.lfilter(self.coefficients, 1, unfiltered, zi=self.filter_state)
        self.outputs["filtered"].write(filtered)



class BandpassFilter(BaseNode):

    def __init__(self, low_cutoff_frequency, high_cutoff_frequency, transition_width, node_count, sample_rate):
        super().__init__()
        self.defineInput("unfiltered")
        self.defineOutput("filtered")
        
        frequencies = [0, low_cutoff_frequency - transition_width, low_cutoff_frequency, high_cutoff_frequency, high_cutoff_frequency + transition_width, sample_rate / 2]
        gain = [0, 0, 1, 1, 0, 0]
        self.coefficients = scipy.signal.firwin2(node_count, frequencies, gain, fs=sample_rate)
        self.filter_state = numpy.zeros(node_count - 1)

    def work(self, sample_count):
        unfiltered = self.inputs["unfiltered"].read(sample_count)
        filtered, self.filter_state = scipy.signal.lfilter(self.coefficients, 1, unfiltered, zi=self.filter_state)
        self.outputs["filtered"].write(filtered)



class PeakFilter(BaseNode):

    def __init__(self, peak_frequency, transition_width, node_count, sample_rate):
        super().__init__()
        self.defineInput("unfiltered")
        self.defineOutput("filtered")
        
        frequencies = [0, peak_frequency - transition_width, peak_frequency, peak_frequency + transition_width, sample_rate / 2]
        gain = [0, 0, 1, 0, 0]
        self.coefficients = scipy.signal.firwin2(node_count, frequencies, gain, fs=sample_rate)
        self.filter_state = numpy.zeros(node_count - 1)

    def work(self, sample_count):
        unfiltered = self.inputs["unfiltered"].read(sample_count)
        filtered, self.filter_state = scipy.signal.lfilter(self.coefficients, 1, unfiltered, zi=self.filter_state)
        self.outputs["filtered"].write(filtered)



class ClockExtractor(BaseNode):

    def __init__(self, frequency, margin, node_count, sampling_rate):
        super().__init__()
        self.defineInput("signal")
        self.defineOutput("clock")

        self.filter = PeakFilter(frequency, margin, node_count, sampling_rate)
        self.filter.outputs["filtered"].registerConsumer(self)

    def work(self, sample_count):
        signal = self.inputs["signal"].read(sample_count)
        squared = signal ** 2
        self.filter.inputs["unfiltered"].write(squared)
        filtered = self.filter.outputs["filtered"].read(sample_count, self)
        rectified = -1 + 2 * (filtered > 0)
        self.outputs["clock"].write(rectified)



class ClockedSampler(BaseNode):

    def __init__(self, block_size):
        super().__init__()
        self.defineInput("original")
        self.defineInput("clock")
        self.defineOutput("sampled")

        self.block_size = block_size

        self.last_clock = 1

    def work(self, sample_count):
        sampled_buf = Buffer()
        while sampled_buf.getSampleCount() < sample_count:
            original = self.inputs["original"].read(self.block_size)
            clock = self.inputs["clock"].read(self.block_size)
            posedge = numpy.diff(numpy.insert(clock, 0, self.last_clock)) > 0
            self.last_clock = clock[-1]
            sampled = numpy.take(original, numpy.nonzero(posedge))[0]
            sampled_buf.write(sampled)
        self.outputs["sampled"].write(sampled_buf.read(sampled_buf.getSampleCount()))



"""
class QuadratureAmplitudeModulator(BaseNode):

    def __init__(self, carrier_frequency, sample_rate):
        super().__init__()
        self.defineInputs(["baseband 1"])
        self.defineInputs(["baseband 2"])
        self.defineOutputs(["modulated"])

        self.oscillator = ManualNode(Oscillator(carrier_frequency, sample_rate))

    def work(self, sample_count):
        baseband1 = self.inputs["baseband 1"].read(sample_count)
        baseband2 = self.inputs["baseband 2"].read(sample_count)
        in_phase = baseband1
        quadrature = baseband2 * 1j
        modulated = self.oscillator.read(sample_count) * (in_phase + quadrature)
        scaled = modulated / numpy.sqrt(2)
        self.outputs["modulated"].write(scaled)



class Repeat(BaseNode):

    def __init__(self, repetition_amount):
        super().__init__()
        self.defineInputs(["signal"])
        self.defineOutputs(["repeated"])

        self.repetition_amount = repetition_amount

        self.buffer = Buffer()

    def work(self, sample_count):
        input_amount = math.ceil((sample_count - self.buffer.getSampleCount()) / self.repetition_amount)
        if input_amount > 0:
            signal = self.inputs["signal"].read(input_amount)
            repeated = numpy.repeat(signal, self.repetition_amount)
            self.buffer.write(repeated)
        self.outputs["repeated"].write(self.buffer.read(sample_count))



class RandomSource(BaseNode):

    def __init__(self):
        super().__init__()
        self.defineOutputs(["random"])

    def work(self, sample_count):
        rand = numpy.random.random(sample_count) * 2 - 1
        self.outputs["random"].write(rand)



class AmplitudeModulator(BaseNode):

    def __init__(self, carrier_frequency, modulation_index, sample_rate):
        super().__init__()
        self.defineInputs(["baseband"])
        self.defineOutputs(["modulated"])

        self.modulation_index = modulation_index

        self.oscillator = ManualNode(Oscillator(carrier_frequency, sample_rate))

    def work(self, sample_count):
        carrier = self.oscillator.read(sample_count)
        baseband = self.inputs["baseband"].read(sample_count)
        normalized = (baseband + 1) / 2
        scaled = normalized * self.modulation_index + (1 - self.modulation_index)
        modulated = carrier * scaled
        self.outputs["modulated"].write(modulated)



class LowPassFilter(BaseNode):

    def __init__(self, cutoff_frequency, transition_width, node_count, sample_rate):
        super().__init__()
        self.defineInputs(["signal"])
        self.defineOutputs(["filtered"])
        
        frequencies = [0, cutoff_frequency, cutoff_frequency + transition_width, sample_rate / 2]
        gain = [1, 1, 0, 0]
        self.coefficients = scipy.signal.firwin2(node_count, frequencies, gain, fs=sample_rate)
        self.filter_state = numpy.zeros(node_count - 1)

    def work(self, sample_count):
        signal = self.inputs["signal"].read(sample_count)
        filtered, self.filter_state = scipy.signal.lfilter(self.coefficients, 1, signal, zi=self.filter_state)
        self.outputs["filtered"].write(filtered)
"""
