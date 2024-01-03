from .nodes import BaseNode, Buffer
import numpy
import math
import threading



class NullSink(BaseNode):

    def __init__(self, block_size):
        super().__init__()
        self.defineInput("samples")
        
        self.block_size = block_size

        self.thread = threading.Thread(target=self._loop)

    def _loop(self):
        while True:
            self.inputs["samples"].read(self.block_size)
    
    def start(self):
        self.thread.start()



class Clock(BaseNode):

    def __init__(self, sample_rate, offset=0):
        super().__init__()
        
        self.defineOutput("time")
        
        self.sample_rate = sample_rate
        self.current_time = offset

    def work(self, sample_count):
        last_sample_time = self.current_time + (sample_count - 1) / self.sample_rate
        time_points = numpy.linspace(self.current_time, last_sample_time, sample_count)
        self.outputs["time"].write(time_points)
        self.current_time += sample_count / self.sample_rate



class Interleaver(BaseNode):

    def __init__(self, input_count):
        super().__init__()

        self.defineInputGroup("deinterleaved", input_count)
        self.defineOutput("interleaved")

        self.input_count = input_count

    def work(self, sample_count):
        input_amount = math.ceil(sample_count / self.input_count)
        interleaved = numpy.empty(sample_count)
        for index in range(self.input_count):
            deinterleaved = self.inputs["deinterleaved"][index].read(input_amount)
            interleaved[index::self.input_count] = deinterleaved
        self.outputs["interleaved"].write(interleaved)



class Deinterleaver(BaseNode):

    def __init__(self, output_count):
        super().__init__()

        self.defineInput("interleaved")
        self.defineOutputGroup("deinterleaved", output_count)

        self.output_count = output_count

    def work(self, sample_count):
        input_amount = sample_count * self.output_count
        interleaved = self.inputs["interleaved"].read(input_amount)
        for index in range(self.output_count):
            deinterleaved = interleaved[index::self.output_count]
            self.outputs["deinterleaved"][index].write(deinterleaved)



class NearestNeighbourResampler(BaseNode):

    def __init__(self, output_ratio):
        super().__init__()

        self.defineInput("original")
        self.defineOutput("resampled")

        self.index_counter = Clock(output_ratio)
        self.index_counter.outputs["time"].registerConsumer(self)

        self.current_index = -1
        self.last_sample = 0

    def work(self, sample_count):
        counter = self.index_counter.outputs["time"].read(sample_count, self)
        indices = numpy.round(counter).astype(numpy.int64) - self.current_index
        input_amount = max(indices)
        new_samples = self.inputs["original"].read(input_amount)
        original = numpy.insert(new_samples, 0, self.last_sample)
        self.last_sample = original[-1]
        self.current_index += input_amount
        resampled = numpy.take(original, indices)
        self.outputs["resampled"].write(resampled)



class PulseResampler(BaseNode):

    def __init__(self, output_ratio):
        super().__init__()

        self.defineInput("original")
        self.defineOutput("resampled")

        self.index_counter = Clock(output_ratio)
        self.index_counter.outputs["time"].registerConsumer(self)

        self.current_index = -1
        self.last_sample = 0

    def work(self, sample_count):
        counter = self.index_counter.outputs["time"].read(sample_count, self)
        indices = numpy.round(counter).astype(numpy.int64) - self.current_index
        input_amount = max(indices)
        new_samples = self.inputs["original"].read(input_amount)
        original = numpy.insert(new_samples, 0, self.last_sample)
        self.last_sample = original[-1]
        self.current_index += input_amount
        resampled = numpy.take(original, indices)
        self.outputs["resampled"].write(resampled)



class GracefulInputBuffer(BaseNode):

    def __init__(self):
        super().__init__()
        self.defineOutput("samples")
        self.defineOutput("present")
    
    def work(self, sample_count):
        fallback = numpy.zeros(sample_count)
        self.outputs["samples"].write(fallback)
        self.outputs["present"].write(numpy.zeros_like(fallback))

    def write(self, samples):
        self.outputs["samples"].write(samples)
        self.outputs["present"].write(numpy.ones_like(samples))



class OutputBuffer(BaseNode):

    def __init__(self):
        super().__init__()
        self.defineInput("samples")

    def read(self, sample_count):
        return self.inputs["samples"].read(sample_count)



class Recorder(BaseNode):

    def __init__(self, block_size):
        super().__init__()
        self.defineInput("audio")
        self.block_size = block_size
        self.recording_done = threading.Condition()
        self.thread = threading.Thread(target=self._threadLoop)
        self.record_count = 0
        self.buffer = Buffer()

    def work(self, sample_count):
        samples = self.inputs["audio"].read(sample_count)
        if self.record_count > 0:
            trimmed = samples[:self.record_count]
            self.buffer.write(trimmed)
            self.record_count -= len(trimmed)
            if self.record_count == 0:
                self.recording_done.acquire()
                self.recording_done.notify()
                self.recording_done.release()

    def _threadLoop(self):
        while True:
            self.work(self.block_size)
    
    def start(self):
        self.thread.start()

    def record(self, sample_count):
        self.recording_done.acquire()
        self.record_count = sample_count
        self.recording_done.wait()
        samples = self.buffer.read(sample_count)
        self.recording_done.release()
        return samples