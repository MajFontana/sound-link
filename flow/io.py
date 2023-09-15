import numpy
import pyaudio
from .nodes import BaseNode
from .basic import Interleaver, Deinterleaver
import threading
import math



class AudioIO(BaseNode):
    
    def __init__(self, sample_width, sample_rate, channel_count, block_size):
        super().__init__()

        self.defineInputGroup("audio_out", channel_count)
        self.defineOutputGroup("audio_in", channel_count)

        self.channel_interleaver = Interleaver(channel_count)
        self.channel_interleaver.outputs["interleaved"].registerConsumer(self)

        self.channel_deinterleaver = Deinterleaver(channel_count)
        for node_output in self.channel_deinterleaver.outputs["deinterleaved"]:
            node_output.registerConsumer(self)

        # TODO: 24 PCM
        self.channel_count = channel_count
        self.sample_rate = sample_rate
        if sample_width == 1:
            self.data_type = numpy.int8
        elif sample_width == 2:
            self.data_type = numpy.int16
        elif sample_width == 4:
            self.data_type = numpy.int32
        
        self.block_size = block_size
        self.new_data_condition = threading.Condition()
        self.pyaudio = pyaudio.PyAudio()
        self.stream = self.pyaudio.open(
            format=self.pyaudio.get_format_from_width(sample_width, True),
            channels=channel_count,
            rate=sample_rate,
            input=True,
            output=True,
            start=False,
            frames_per_buffer=block_size,
            stream_callback=self._IOCallback
            )
        
    def _IOCallback(self, bytes_in, frame_count, time_info, status):
        type_info = numpy.iinfo(self.data_type)
    
        real_in = numpy.frombuffer(bytes_in, dtype=self.data_type)
        normalized_in = numpy.interp(real_in, [type_info.min, type_info.max], [-1, 1])
        self.channel_deinterleaver.inputs["interleaved"].write(normalized_in)
        for index in range(self.channel_count):
            samples = self.channel_deinterleaver.outputs["deinterleaved"][index].read(frame_count, self)
            self.outputs["audio_in"][index].write(samples)
        with self.new_data_condition:
            self.new_data_condition.notify()
        
        output_amount = frame_count * self.channel_count
        for index in range(self.channel_count):
            samples = self.inputs["audio_out"][index].read(frame_count)
            self.channel_interleaver.inputs["deinterleaved"][index].write(samples)
        normalized_out = self.channel_interleaver.outputs["interleaved"].read(output_amount, self)
        real_out = numpy.interp(normalized_out.real, [-1, 1], [type_info.min, type_info.max])
        bytes_out = real_out.round().astype(self.data_type).tobytes()

        return (bytes_out, pyaudio.paContinue)

    def start(self):
        self.stream.start_stream()

    def work(self, sample_count):
        for _ in range(math.ceil(sample_count / self.block_size)):
            with self.new_data_condition:
                self.new_data_condition.wait()