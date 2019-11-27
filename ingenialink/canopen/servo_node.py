import canopen
import struct
import time
import xml.etree.ElementTree as ET

from .._utils import *
from .constants import *
from .._ingenialink import ffi, lib
from .dictionary import DictionaryCANOpen
from .registers import Register, REG_DTYPE, REG_ACCESS


class Servo(object):
    def __init__(self, net, node, dict):
        self.__net = net
        self.__node = node
        self.__dict = DictionaryCANOpen(dict)
        self.__info = {}
        self.init_info()

    def init_info(self):
        name = "Drive"
        serial_number = self.raw_read('SERIAL_NUMBER')
        product_code = self.raw_read('PRODUCT_CODE')
        sw_version = self.raw_read('SOFTWARE_VERSION')
        revision_number = self.raw_read('REVISION_NUMBER')
        hw_variant = 'A'

        self.__info = {
            'serial': serial_number,
            'name': name,
            'sw_version': sw_version,
            'hw_variant': hw_variant,
            'prod_code': product_code,
            'revision': revision_number
        }

    def raw_read(self, reg):
        """ Raw read from servo.

            Args:
                reg (Register): Register.

            Returns:
                int: Otained value

            Raises:
                TypeError: If the register type is not valid.
        """

        if isinstance(reg, Register):
            _reg = reg
        elif isinstance(reg, str):
            _dict = self.__dict
            if not _dict:
                raise ValueError('No dictionary loaded')

            _reg = _dict.regs[reg]
        else:
            raise TypeError('Invalid register')

        access = _reg.access
        if access == REG_ACCESS.WO:
            raise TypeError('Register is Write-only')

        dtype = _reg.dtype
        try:
            if dtype == REG_DTYPE.S8:
                value = int.from_bytes(self.__node.sdo.upload(int(_reg.idx, 16), int(_reg.subidx, 16)), "little",
                                       signed=True)
            elif dtype == REG_DTYPE.S16:
                value = int.from_bytes(self.__node.sdo.upload(int(_reg.idx, 16), int(_reg.subidx, 16)), "little",
                                       signed=True)
            elif dtype == REG_DTYPE.S32:
                value = int.from_bytes(self.__node.sdo.upload(int(_reg.idx, 16), int(_reg.subidx, 16)), "little",
                                       signed=True)
            elif dtype == REG_DTYPE.FLOAT:
                [value] = struct.unpack('f', self.__node.sdo.upload(int(_reg.idx, 16), int(_reg.subidx, 16)))
            elif dtype == REG_DTYPE.STR:
                value = self.__node.sdo.upload(int(_reg.idx, 16), int(_reg.subidx, 16)).decode("utf-8")
            else:
                value = int.from_bytes(self.__node.sdo.upload(int(_reg.idx, 16), int(_reg.subidx, 16)), "little")
        except Exception as e:
            print(e)
            raise("Read error")
        return value

    def read(self, reg):
        """ Read from servo.

            Args:
                reg (str, Register): Register.

            Returns:
                float: Otained value

            Raises:
                TypeError: If the register type is not valid.
        """
        return self.raw_read(reg)

    def write(self, reg, data, confirm=True, extended=0):
        return self.raw_write(reg, data, confirm=True, extended=0)

    def raw_write(self, reg, data, confirm=True, extended=0):
        """ Raw write to servo.

            Args:
                reg (Register): Register.
                data (int): Data.
                confirm (bool, optional): Confirm write.
                extended (int, optional): Extended frame.

            Raises:
                TypeError: If any of the arguments type is not valid or
                    unsupported.
        """

        if isinstance(reg, Register):
            _reg = reg
        elif isinstance(reg, str):
            _dict = self.__dict
            if not _dict:
                raise ValueError('No dictionary loaded')

            _reg = _dict.regs[reg]
        else:
            raise TypeError('Invalid register')

        if _reg.access == REG_ACCESS.RO:
            raise TypeError('Register is Read-only')

        # auto cast floats if register is not float
        if isinstance(data, float) and _reg.dtype != REG_DTYPE.FLOAT:
            data = int(data)

        try:
            if _reg.dtype == REG_DTYPE.FLOAT:
                self.__node.sdo.download(int(_reg.idx, 16), int(_reg.subidx, 16),
                                         struct.pack('f', data))
            else:
                bytes_length = 2
                signed = False
                if _reg.dtype == REG_DTYPE.U16:
                    bytes_length = 2
                elif _reg.dtype == REG_DTYPE.S16:
                    bytes_length = 2
                    signed = True
                elif _reg.dtype == REG_DTYPE.U32:
                    bytes_length = 4
                elif _reg.dtype == REG_DTYPE.S32:
                    bytes_length = 4
                    signed = True

                self.__node.sdo.download(int(_reg.idx, 16), int(_reg.subidx, 16),
                                         data.to_bytes(bytes_length, byteorder='little', signed=signed))
        except Exception as e:
            print(_reg.identifier + " : " + e)
            raise ("Write error")

    def get_all_registers(self):
        for obj in self.__node.object_dictionary.values():
            print('0x%X: %s' % (obj.index, obj.name))
            if isinstance(obj, canopen.objectdictionary.Record):
                for subobj in obj.values():
                    print('  %d: %s' % (subobj.subindex, subobj.name))

    def dict_storage_read(self, new_path):
        """Read all dictionary registers content and put it to the dictionary
        storage."""

        with open(self.__dict.dict, 'r+') as xml_file:
            tree = ET.parse(xml_file)
        root = tree.getroot()

        for element in root.findall('./Body/Device/Registers/Register'):
            try:
                if element.attrib['access'] == 'rw':
                    storage = self.raw_read(element.attrib['id'])
                    element.set('storage', str(storage))

                    # Update register object
                    reg = self.__dict.regs[element.attrib['id']]
                    reg.storage = storage
                    reg.storage_valid = 1
            except Exception as e:
                # print("Exception during dict_storage_read, register " + element.attrib['id'] + ": ", str(e))
                pass

        tree.write(new_path)
        xml_file.close()

    def dict_storage_write(self, path):
        """Write current dictionary storage to the servo drive."""
        with open(path, 'r+') as xml_file:
            tree = ET.parse(xml_file)
        root = tree.getroot()

        for element in root.findall('./Body/Device/Registers/Register'):
            try:
                if 'storage' in element.attrib and element.attrib['access'] == 'rw':
                    self.raw_write(element.attrib['id'], float(element.attrib['storage']))
            except Exception as e:
                # print("Exception during dict_storage_write, register " + element.attrib['id'] + ": ", str(e))
                pass

    def store_all(self):
        """ Store all servo current parameters to the NVM. """
        r = 0
        try:
            self.raw_write("STORE_ALL", 0x65766173)
        except:
            r = -1
        return r

    def dict_load(self, dict_f):
        """ Load dictionary.

            Args:
                dict_f (str): Dictionary.
        """
        try:
            self.__dict = DictionaryCANOpen(dict_f)
        except Exception as e:
            print("Error loading a dictionary")

    def state_subscribe(self, cb):
        """ Subscribe to state changes.

            Args:
                cb: Callback

            Returns:
                int: Assigned slot.
        """
        return 0

    def enable(self, timeout=2.):
        """ Enable PDS.

            Args:
                timeout (int, float, optional): Timeout (s).
        """

        r = lib.il_servo_enable(self.__node, to_ms(timeout))
        raise_err(r)

    def status_word_decode(self, status_word):
        state = lib.IL_SERVO_STATE_NRDY
        if (status_word & IL_MC_PDS_STA_NRTSO_MSK) == IL_MC_PDS_STA_NRTSO:
            state = lib.IL_SERVO_STATE_NRDY
        elif (status_word & IL_MC_PDS_STA_SOD_MSK) == IL_MC_PDS_STA_SOD:
            state = lib.IL_SERVO_STATE_DISABLED
        elif (status_word & IL_MC_PDS_STA_RTSO_MSK) == IL_MC_PDS_STA_RTSO:
            state = lib.IL_SERVO_STATE_RDY
        elif (status_word & IL_MC_PDS_STA_SO_MSK) == IL_MC_PDS_STA_SO:
            state = lib.IL_SERVO_STATE_ON
        elif (status_word & IL_MC_PDS_STA_OE_MSK) == IL_MC_PDS_STA_OE:
            state = lib.IL_SERVO_STATE_ENABLED
        elif (status_word & IL_MC_PDS_STA_QSA_MSK) == IL_MC_PDS_STA_QSA:
            state = lib.IL_SERVO_STATE_QSTOP
        elif (status_word & IL_MC_PDS_STA_FRA_MSK) == IL_MC_PDS_STA_FRA:
            state = lib.IL_SERVO_STATE_FAULTR
        elif (status_word & IL_MC_PDS_STA_F_MSK) == IL_MC_PDS_STA_F:
            state = lib.IL_SERVO_STATE_FAULT
        return state

    def status_word_wait_change(self, status_word, timeout):
        r = 0
        start_time = int(round(time.time() * 1000))
        actual_status_word = self.raw_read('STATUS_WORD')
        while actual_status_word == status_word or r != lib.IL_ETIMEDOUT:
            current_time = int(round(time.time() * 1000))
            if current_time - start_time > timeout:
                r = lib.IL_ETIMEDOUT
            actual_status_word = self.raw_read('STATUS_WORD')
        return r

    def fault_reset(self):
        r = 0
        retries = 0
        status_word = self.raw_read('STATUS_WORD')
        status_word_decoded = self.status_word_decode(status_word)
        while status_word_decoded == lib.IL_SERVO_STATE_FAULT or status_word_decoded == lib.IL_SERVO_STATE_FAULTR:
            # Check if faulty, if so try to reset (0->1)
            if retries == FAULT_RESET_RETRIES:
                return lib.IL_ESTATE
            self.raw_write('CONTROL_WORD', 0)
            self.raw_write('CONTROL_WORD', IL_MC_CW_FR)
            # Wait until statusword changes
            r = self.status_word_wait_change(PDS_TIMEOUT, status_word)
            if r < 0:
                return r
            retries += 1
        return r

    def disable(self):
        """ Disable PDS. """
        r = 0
        status_word = self.raw_read('STATUS_WORD')
        status_word_decoded = self.status_word_decode(status_word)
        while status_word_decoded != lib.IL_SERVO_STATE_DISABLED:
            # Try fault reset if faulty
            if status_word_decoded == lib.IL_SERVO_STATE_FAULT or status_word_decoded == lib.IL_SERVO_STATE_FAULTR:
                r = self.fault_reset()
                if r < 0:
                    return r
            elif status_word_decoded == lib.IL_SERVO_STATE_DISABLED:
                self.raw_write('CONTROL_WORD', IL_MC_PDS_CMD_DV)
                # Wait until statusword changes
                r = self.status_word_wait_change(PDS_TIMEOUT, status_word)
                if r < 0:
                    return r
            status_word = self.raw_read('STATUS_WORD')
            status_word_decoded = self.status_word_decode(status_word)
        raise_err(r)

    @property
    def dict(self):
        """ Dictionary: Dictionary. """
        return self.__dict

    @property
    def errors(self):
        """ dict: Errors. """
        return self.__dict.errors

    @property
    def info(self):
        """ dict: Servo information. """
        return self.__info

    @property
    def state(self):
        """ tuple: Servo state and state flags. """
        return lib.IL_SERVO_STATE_NRDY
