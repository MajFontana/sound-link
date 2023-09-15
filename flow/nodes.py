import numpy
import threading



class Buffer:

    def __init__(self):
        self.array = numpy.array([])

    def getSampleCount(self):
        return len(self.array)
    
    def read(self, sample_count):
        output_samples = self.array[:sample_count]
        self.array = self.array[sample_count:]
        return output_samples

    def write(self, samples):
        self.array = numpy.concatenate([self.array, samples])



class NodeInput:

    def __init__(self):
        self.producer = None
        self.buffer = Buffer()

    def assignProducer(self, producer):
        self.producer = producer
        producer.registerConsumer(self)

    def read(self, sample_count):
        available_amount = min(sample_count, self.buffer.getSampleCount())
        missing_amount = sample_count - available_amount
        samples = self.buffer.read(available_amount)
        if self.producer != None:
            samples = numpy.concatenate([samples, self.producer.read(missing_amount, self)])
        else:
            samples = numpy.concatenate([samples, numpy.zeros(missing_amount)])
        return samples
    
    def write(self, samples):
        self.buffer.write(samples)



class NodeOutput:

    def __init__(self, parent_node):
        self.parent_node = parent_node
        self.thread_lock = threading.Lock()
        self.buffers = {}
        self.locked = False

    def registerConsumer(self, consumer):
        self.buffers[consumer] = Buffer()

    def read(self, sample_count, consumer):
        buffer = self.buffers[consumer]
        self.thread_lock.acquire()
        if buffer.getSampleCount() < sample_count:
            self.parent_node.work(sample_count - buffer.getSampleCount())
        samples = buffer.read(sample_count)
        self.thread_lock.release()
        return samples

    def write(self, samples):
        for buffer in self.buffers.values():
            buffer.write(samples)



class BaseNode:

    def __init__(self):
        self.inputs = {}
        self.outputs = {}

    def defineInput(self, key):
        self.inputs[key] = NodeInput()
    
    def defineOutput(self, key):
        self.outputs[key] = NodeOutput(self)
    
    def defineInputGroup(self, key, count):
        self.inputs[key] = [NodeInput() for _ in range(count)]
    
    def defineOutputGroup(self, key, count):
        self.outputs[key] = [NodeOutput(self) for _ in range(count)]



"""
class StandaloneNode:

    def __init__(self, node):
        self.node = node
        self.inputs = {}
        self.outputs = {}

        if output_keys == None:
            output_keys = node.outputs.keys()

        for key in node.inputs:
            self.inputs[key] = NodeOutput(self)
            node.inputs[key].connectTo(self.inputs[key])

        for key in output_keys:
            self.outputs[key] = NodeInput()
            self.outputs[key].connectTo(node.outputs[key])

    def enableOutput(self, key, index=None):
        self.outputs[key] = NodeInput()
        self.outputs[key].connectTo(node_output.outputs[key])
"""
