import asyncio
from struct import pack, unpack

from pyee import EventEmitter


# message types
DATA_CHANNEL_ACK = 2
DATA_CHANNEL_OPEN = 3

# channel types
DATA_CHANNEL_RELIABLE = 0

WEBRTC_DCEP = 50
WEBRTC_STRING = 51


class DataChannelManager:
    def __init__(self, pc, endpoint):
        self.channels = {}
        self.endpoint = endpoint
        self.pc = pc
        if endpoint.is_server:
            self.stream_id = 0
        else:
            self.stream_id = 1

    def create_channel(self, label, protocol):
        # register channel
        channel = RTCDataChannel(id=self.stream_id, label=label, protocol=protocol,
                                 manager=self)
        self.channels[channel.id] = channel
        self.stream_id += 2

        # open channel
        data = pack('!BBHLHH', DATA_CHANNEL_OPEN, DATA_CHANNEL_RELIABLE,
                    0, 0, len(label), len(protocol))
        data += label.encode('utf8')
        data += protocol.encode('utf8')
        asyncio.ensure_future(self.endpoint.send(channel.id, WEBRTC_DCEP, data))

        return channel

    def send(self, channel, data):
        asyncio.ensure_future(self.endpoint.send(channel.id, WEBRTC_STRING, data.encode('utf8')))

    async def run(self, endpoint):
        self.endpoint = endpoint
        while True:
            stream_id, pp_id, data = await self.endpoint.recv()
            if pp_id == WEBRTC_DCEP and len(data):
                msg_type = unpack('!B', data[0:1])[0]
                if msg_type == DATA_CHANNEL_OPEN and len(data) >= 12:
                    # one side should be using even IDs, the other odd IDs
                    assert (stream_id % 2) != (self.stream_id % 2)
                    assert stream_id not in self.channels

                    (msg_type, channel_type, priority, reliability,
                     label_length, protocol_length) = unpack('!BBHLHH', data[0:12])
                    pos = 12
                    label = data[pos:pos + label_length].decode('utf8')
                    pos += label_length
                    protocol = data[pos:pos + protocol_length].decode('utf8')

                    # register channel
                    channel = RTCDataChannel(id=stream_id, label=label, protocol=protocol,
                                             manager=self)
                    self.channels[stream_id] = channel

                    # emit channel
                    self.pc.emit('datachannel', channel)
            elif pp_id == WEBRTC_STRING and stream_id in self.channels:
                # emit message
                self.channels[stream_id].emit('message', data.decode('utf8'))


class RTCDataChannel(EventEmitter):
    def __init__(self, id, label, protocol, manager, loop=None):
        super().__init__(loop=loop)
        self.__id = id
        self.__label = label
        self.__manager = manager
        self.__protocol = protocol

    def close(self):
        pass

    def send(self, data):
        self.__manager.send(self, data)

    @property
    def id(self):
        """
        An ID number which uniquely identifies the data channel.
        """
        return self.__id

    @property
    def label(self):
        """
        A name describing the data channel.

        These labels are not required to be unique.
        """
        return self.__label

    @property
    def protocol(self):
        """
        The name of the subprotocol in use.
        """
        return self.__protocol