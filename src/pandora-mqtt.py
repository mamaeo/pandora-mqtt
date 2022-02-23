
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from os import getenv
from cmd import Cmd
import argparse
import struct
import time
import sys
import re

COLOR_TO_HEX = {
    'white': 7,
    'red': 1,
    'off': 0,
    'green': 2,
    'blue': 4
}

UPDATE_COMMAND = 0
LIGHT_COMMAND = 1
DRAIN_COMMAND = 2
AUTO_COMMAND = 3
FORCE_UPDATE_COMMAND = 4

# Load options from .env
load_dotenv()

# Some public variables
verbose = False
commands = list()
mqtt_broker_url = getenv('MQTT_BROKER')
mqtt_broker_port = int(getenv('MQTT_PORT'))
prefix = 'pandora/{}/'.format(getenv('APP_USERNAME'))
topics = list()


class Interactive(Cmd):

    intro = 'Welcome to Pandora mqtt prompt shell. \tType help or ? to list commands.\n'
    prompt = '(cli) $'
    file = None
    _exit = False

    def __init__(self, mqttClient):
        super(Interactive, self).__init__()
        self._client = mqttClient


    @staticmethod
    def parse(args_as_string, args_type=None, default=None):
        'Convert each separated string into an argument tuple'
        args = list(map(str, args_as_string.split()))
        # Replace missing values with those defined in default tuple
        if default and len(default) > len(args):
            args.extend(default[len(args): ])
        if args_type:
            # Assert type
            assert len(args_type) == len(args), \
                StopIteration('Number of types does not match the number of arguments')
            # Change primitive value of each of the parameters
            for arg, i in zip(args, range(len(args))):
                try:
                    # Convert argument to his specified type
                    args[i] = args_type[i](arg)
                except Exception:
                    raise ValueError('Cannot cast value {} to type {}'
                        .format(args[i], args_type[i]))
        return args

    
    @staticmethod
    def parseTimeRange(range_as_string):
        # Check string format before
        # i.e time range 12:15-14:30
        regex = '(?P<start_h>[0-9]{2}):(?P<start_m>[0-9]{2})-(?P<end_h>[0-9]{2}):(?P<end_m>[0-9]{2})'
        match = re.search(regex, range_as_string)
        if not match:
            raise ValueError('Invalid time range format')
        return tuple(map(int, match.groups()))



    def do_exit(self, inp):
        # Disconnect from client
        self._client.disconnect()
        self._exit = True
        return True


    def do_subscribe(self, args):
        # Unpack arguments
        [_topic, add_prefix] = Interactive.parse(args, args_type=(str, bool), default=['#', True])
        if add_prefix:
            _topic = prefix + _topic
        # Append new topic to the list
        result, mid = self._client.subscribe(_topic)
        if not mid:
            raise ConnectionError(result)
        # If subscribtion is succed then add new element to the list
        topics.append(_topic)

    
    def help_subscribe(self):
        print('This function can be used to subscribe to a new topic.\n' \
                'The argument accepted by this function must be a string indicating ' \
                'the path of the topic you want to subscribe and a boolean indicating' \
                'whether the topic must be preceded by the prefix {}'
                    .format(self._prefix), 
                file=sys.stderr)

    
    def do_unsubscribe(self, args):
        # Assert that user is subscribed to at least one topic
        assert len(topics) > 0, \
            ValueError('You must be subscribed to at least one topic')
        # Unpack arguments
        [topic_code, ] = Interactive.parse(args, args_type=(int, ), default=[-1])
        # If topic is None then remove last element
        code, mid = self._client.unsubscribe(topics[topic_code])
        if not mid:
            raise ConnectionError(code)
        # If unsubscribed then remove last element of the list
        topics.pop(topic_code)

    
    def help_unsubscribe(self):
        print('This function can be used to unsubscribe from any topic.\n' \
                'The argument accepted by this function ' \
                'must be a number indicating the topic\'s code.\nYou can print topic codes ' \
                'calling $list command. Topic code -1 indicates the last topic in the list', 
            file=sys.stderr)

    
    def do_list(self, args):
        for code, topic in zip(range(len(topics)), topics):
            print('[{}] {}'.format(code, topic))

    
    def help_list(self):
        print('Print the topics followed with their codes.', file=sys.stderr)


    def do_drain(self, args):
        # Assert that user is subscribed to at least one topic
        assert len(topics) > 0, \
            ValueError('You must be subscribed to at least one topic')
        # Unpack arguments
        [is_on, limit, topic_code, qos] = Interactive.parse(args, 
            args_type=(bool, int, int, int), default=[True, 10, -1, 0])
        try:       
             # Pack message as string of bytes
            info = self._client.publish(topics[topic_code], 
                struct.pack('<B3xI?3xIf', DRAIN_COMMAND, 0, is_on, limit, time.time()), qos=qos)
        except (ValueError, RuntimeError):
            raise Exception(info.rc)

    
    def help_drain(self):
        pass
    

    def do_light(self, args):
        # Assert that user is subscribed to at least one topic
        assert len(topics) > 0, \
            ValueError('You must be subscribed to at least one topic')
        # Unpack arguments
        [color, limit, topic_code, qos] = Interactive.parse(args, 
            args_type=(str, int, int, int), default=['white', 60, -1, 0])
        try:       
             # Pack message as string of bytes
            info = self._client.publish(topics[topic_code], 
                struct.pack('<B3xIB3xIf', LIGHT_COMMAND, 0, COLOR_TO_HEX[color], limit, 
                time.time()), qos=qos)
        except (ValueError, RuntimeError):
            raise Exception(info.rc)
            

    def do_auto(self, args):
        # Assert that user is subscribed to at least one topic
        assert len(topics) > 0, \
            ValueError('You must be subscribed to at least one topic')
        # Unpack arguments
        [is_on, dryness_max, d_limit, brightness_min, l_limit, topic_code, qos] = Interactive.parse(args, 
            args_type=(bool, int, str, int, str, int, int), 
            default=[True, 0, '00:00-00:00', 0, '00:00-00:00', -1, 0])
        try:       
             # Pack message as string of bytes
            self._client.publish(topics[topic_code], 
                struct.pack('<B3xI?3xH2xBBBBH2xBBBBf', AUTO_COMMAND, 0, is_on, dryness_max, 
                    *Interactive.parseTimeRange(d_limit), brightness_min, 
                    *Interactive.parseTimeRange(l_limit), time.time()), 
                qos)
        except (ValueError, RuntimeError) as err:
            raise Exception(err)

    
    def do_force_update(self, args):
         # Assert that user is subscribed to at least one topic
        assert len(topics) > 0, \
            ValueError('You must be subscribed to at least one topic')
        # Unpack arguments
        [is_on, topic_code, qos] = Interactive.parse(args, 
            args_type=(bool, int, int), default=[True, -1, 0])
        try:       
             # Pack message as string of bytes
            info = self._client.publish(topics[topic_code], 
                struct.pack('<B3xI?3xf', FORCE_UPDATE_COMMAND, 0, is_on, time.time()), qos=qos)
        except (ValueError, RuntimeError):
            raise Exception(info.rc)


    def cmdloop(self, intro=None) -> None:
        while not self._exit:
            try:
                # Execute main loop
                super().cmdloop(intro)
            except Exception as err:
                print(err, file=sys.stderr)
            


''' Define some useful functions '''

def on_connect(client, userdata, flags, rc):
    if verbose:
        print('Connected to broker {} on port {}'.format(mqtt_broker_url, mqtt_broker_port),
            file=sys.stderr)


def on_disconnect(client, userdata, rc):
    if verbose:
        print('Disconnected from broker {}'.format(mqtt_broker_url), file=sys.stderr)


def on_message(client, userdata, message):
    # Decipher message
    if verbose:
        print('Message received on topic {}'.format(message.topic), file=sys.stderr)
    # Decapsulate message
    [tos, id] = struct.unpack('<B3xI', message.payload[:8])

    if tos == UPDATE_COMMAND:
        sensors = struct.unpack('<HHff?3xI', message.payload[8: ])
        if 'all' in commands or 'UPDATE' in commands:
            # You can change here sensor output format 
            # (i.e If you wish to store it in .csv file or something like that)
            print('UPDATE -> dryness={}\tbrightness={}\thumidity={}\t' \
                'temperature={}\tcapacity={}\torigin={}'
                    .format(*sensors[: 5], time.asctime(time.localtime(sensors[5]))), 
                file=sys.stdout)

    elif tos == LIGHT_COMMAND:
        light_command_fmt = struct.unpack('<B3xII', message.payload[8: ])
        if 'all' in commands or 'LIGHT' in commands:
            print('LIGHT -> rgb={}\tlimit={}\torigin={}'.format(*light_command_fmt[:2], 
                time.asctime(time.localtime(light_command_fmt[2]))), file=sys.stdout)

    elif tos == DRAIN_COMMAND:
        drain_command_fmt = struct.unpack('<?3xII', message.payload[8: ])
        if 'all' in commands or 'DRAIN' in commands:
            print('DRAIN -> is_on={}\tlimit={}\torigin={}'.format(*drain_command_fmt[:2], 
                time.asctime(time.localtime(drain_command_fmt[2]))), file=sys.stdout)

    elif tos == AUTO_COMMAND:
        auto_command_fmt = struct.unpack('<?3xH2xBBBBH2xBBBBI', message.payload[8: ])
        if 'all' in commands or 'AUTO' in commands:
            print('AUTO -> is_on={}\tdryness_max={}\ttime_action_limit=(from {}:{} to {}:{})\t' \
                'brightness_min={}\ttime_action_limit=(from {}:{} to {}:{})\torigin={}'
                    .format(*auto_command_fmt[:10], time.asctime(time.localtime(auto_command_fmt[10]))), 
                file=sys.stdout)

    elif tos == FORCE_UPDATE_COMMAND:
        force_update_command_fmt = struct.unpack('<B3xI', message.payload[8: ])
        if 'all' in commands or 'FORCE_UPDATE' in commands:
            print('FORCE_UPDATE -> is_on={}\torigin={}'.format(force_update_command_fmt[0], 
                time.asctime(time.localtime(force_update_command_fmt[1]))), file=sys.stdout)

    else:
        print('Command not found', file=sys.stderr)


def main():

    global verbose, mqtt_broker_url, mqtt_broker_port, topics, commands

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', dest='verbose',
                        default=False, action='store_true', help='Enable verbose mode')
    parser.add_argument('-c', '--print-commands', dest='commands', action='append',
                        default=list(), help='Choose what commands whould you like to print')
    parser.add_argument('-u', '--broker-url', dest='broker_url', type=str, 
                        default=mqtt_broker_url, help='MQTT broker url')
    parser.add_argument('-p', '--broker-port', dest='broker_port', type=int, 
                        default=mqtt_broker_port, help='MQTT broker port')
    parser.add_argument('-s', '--subscribe', dest='topics', action='append',
                        default=list(), help='Subscribe to any topic')
    parser.add_argument('-d', '--disable-shell', dest='no_shell', action='store_true', 
                        default=False, help='Disable shell')

    args = parser.parse_args()

    verbose = args.verbose
    mqtt_broker_url = args.broker_url
    mqtt_broker_port = args.broker_port
    topics = args.topics
    commands = args.commands

    try:

        # Create mqtt client
        client = mqtt.Client()
        # Try to connect to mqtt broker
        client.connect(mqtt_broker_url, mqtt_broker_port)

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message

        client.loop_start()

        # Subscribe to one or more topics (you can also subscribe later)
        if topics:
            for pos, topic in zip(range(len(topics)), topics):
                if topic.startswith('$/'):
                    topics[pos] = topic.replace('$/', prefix)
                code, mid = client.subscribe(topic)
                if not mid:
                    raise ConnectionError(code)

    except ConnectionError as err:
        print(err)
        # Exit with error code
        sys.exit(-1)
    
    try:
        try:
            # If user disable shell with option -d, then loop forever
            if args.no_shell:
                while True:
                    pass
            # Start interactive shell
            Interactive(client).cmdloop()
        except TimeoutError:
            client.reconnect()
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        sys.stdout.close()
        sys.stderr.close()
        sys.exit(0)


if __name__ == '__main__':
    main()
