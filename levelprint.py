import sys
import struct
from collections import namedtuple
from time import sleep
from pathlib import Path
import os
import io
import zlib
import math
from PIL import Image
from xml.etree.ElementTree import Element, SubElement, Comment, tostring
from xml.dom import minidom
from xml.etree import ElementTree

import hashlib

def _exit(msg):
    print(msg)
    print("Exiting in 1 second..")
    sleep(1)
    sys.exit(-1)

# https://docs.python.org/3/library/struct.html#format-characters

# meta.dat
# I: string count
# [
# H: string length
# str: filename
# ]

def prettifyXML(elem):
    rough_string = ElementTree.tostring(elem, "utf8")
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


"""
    uint32_t wfLZ_GetMaxCompressedSize( const uint32_t inSize )
    {
        return
            // header
            sizeof( wfLZ_Header )
            +
            // size of uncompressible data
            (inSize/WFLZ_MAX_SEQUENTIAL_LITERALS + 1) * (WFLZ_MAX_SEQUENTIAL_LITERALS+WFLZ_BLOCK_SIZE)
            +
            // terminating block
            WFLZ_BLOCK_SIZE;
    }

    void CompressFake( uint8_t* dst, const uint8_t* src, uint32_t len )
    {
      // this assumes 'dst' is already allocated and has enough space, see wfLZ_GetMaxCompressedSize

      // how many command blocks will this require? (rounded up)
      uint32_t numCmdBlocks = (len+WFLZ_BLOCK_SIZE-1)/WFLZ_BLOCK_SIZE;

      // include the end block
      ++numCmdBlocks;

      // write the header
      wfLZ_Header* header = (wfLZ_Header*)dst;
      header->sig[0] = 'W';
      header->sig[1] = 'F';
      header->sig[2] = 'L';
      header->sig[3] = 'Z';
      header->compressedSize = len + numCmdBlocks*WFLZ_BLOCK_SIZE;
      header->uncompressedSize = len;
      dst += sizeof(wfLZ_Header);

      // output the data with interspersed command blocks
      while( len )
      {
        wfLZ_Block* block = (wfLZ_Block*)dst;
        block->dist = 0;
        block->length = 0;
        block->numLiterals = WFLZ_MAX_SEQUENTIAL_LITERALS;
        dst += sizeof(wfLZ_Block);
        uint32_t numCopy = len > WFLZ_MAX_SEQUENTIAL_LITERALS ? WFLZ_MAX_SEQUENTIAL_LITERALS : len ;
        memcpy( dst, src, numCopy );
        dst += numCopy;
        len -= numCopy;
      }

      // output the end block
      wfLZ_Block* block = (wfLZ_Block*)dst;
      block->dist = 0;
      block->length = 0;
      block->numLiterals = 0;
    }
"""

class WFLZ:
    def decomp_bytearr(self, bytearr):
        return bytearr
    def comp_bytearr(self, bytearr):
        print()
        return bytearr
    def decomp_file(self, file):
        start_pos = file.tell()

        wfLZ_Header = struct.unpack("III", file.read(0xC))
        # wfLZ_HeaderChunked = struct.unpack("IIII", file.read(0x10))
        magic = wfLZ_Header[0]
        compressedSize = wfLZ_Header[1]
        decompressedSize = wfLZ_Header[2]

        firstBlock = struct.unpack("HBB", file.read(0x4))
        # dist = firstBlock[0]
        # length = firstBlock[1]
        numLiterals = firstBlock[2]

        dist = -1
        len = -1

        outarray = bytearray(decompressedSize)
        outindex = 0

        WFLZ_BLOCK_SIZE = 4
        WFLZ_MIN_MATCH_LEN = WFLZ_BLOCK_SIZE + 1
        WFLZ_MAX_MATCH_LEN = (0xFF - 1) + WFLZ_MIN_MATCH_LEN

        while 1:
            if numLiterals != 0:
                while numLiterals > 0:
                    outarray[outindex] = struct.unpack("B", file.read(0x1))[0]
                    outindex += 1
                    numLiterals -= 1
            elif dist == 0 and len == 0:
                return outarray

            block = struct.unpack("HBB", file.read(0x4))
            dist = block[0]
            len = block[1]
            numLiterals = block[2]

            if len != 0:
                cpySrc = outindex - dist;
                len += WFLZ_MIN_MATCH_LEN - 1;
                for i in range(len):
                    outarray[outindex] = outarray[cpySrc + i]
                    outindex += 1
        return outarray
    # Thanks Shane!
    def comp_file(self, file):
        return bytearray(0)

def ReadType(file, type):
    return struct.unpack(type, file.read({ "B": 1, "H": 2, "I": 4 }[type]))[0]
def ReadTypeBE(file, type):
    return struct.unpack(">" + type, file.read({ "B": 1, "H": 2, "I": 4 }[type]))[0]
def ReadRSDKString(file):
    return file.read(ReadType(file, "B")).decode("utf8").split('\0', 1)[0]
def ReadString(file):
    str = ""
    bb = ReadType(file, "B")
    while bb != 0:
        str += "%c" % bb
        bb = ReadType(file, "B")
    return str
def ReadCompressed(file, type):
    compressedSize = ReadType(file, "I") - 4
    decompressedSize = ReadTypeBE(file, "I")
    buff = file.read(compressedSize)
    buff = zlib.decompress(buff)

    typesize = { "B": 1, "H": 2, "I": 4 }[type]
    count = len(buff) / typesize

    return struct.unpack(str(count) + type, buff)

def WriteType(file, type, value):
    file.write(struct.pack(type, value))
def WriteTypeBE(file, type, value):
    file.write(struct.pack(">" + type, value))
def WriteRSDKString(file, value):
    WriteType(file, "B", len(value))
    file.write(bytearray(value, "utf8"))
def WriteCompressed(file, type, value):
    typesize = { "B": 1, "H": 2, "I": 4 }[type]

    count = len(value)
    decompressedSize = count * typesize
    buff = struct.pack(str(count) + type, *value)
    buff = zlib.compress(buff)

    compressedSize = len(buff)
    WriteType(file, "I", compressedSize + 4)
    WriteTypeBE(file, "I", decompressedSize)
    file.write(buff)

def ROL4(n, d):
    n &= 0xFFFFFFFF
    return ((n << d) | (n >> (32 - d))) & 0xFFFFFFFF
def ROR4(n, d):
    n &= 0xFFFFFFFF
    return ((n >> d) | (n << (32 - d)) & 0xFFFFFFFF) & 0xFFFFFFFF
# The cleaner source: http://www.burtleburtle.net/bob/hash/doobs.html
def YCG_Hash(string, length, initialHash):
    stringBytes = string.encode("utf8")
    stringBuff = io.BytesIO(stringBytes)

    index = 0
    hashA = (length + initialHash + 0xDEADBEEF) & 0xFFFFFFFF
    hashB = (length + initialHash + 0xDEADBEEF) & 0xFFFFFFFF
    hashC = (length + initialHash + 0xDEADBEEF) & 0xFFFFFFFF

    while length > 12:
        sHashA = hashA
        sHashB = hashB
        sHashC = hashC
        for i in range(min(length, 4)):
            sHashC += ReadType(stringBuff, "B") << ((i & 3) << 3)
            sHashC &= 0xFFFFFFFF
            length -= 1
        for i in range(min(length, 4)):
            sHashB += ReadType(stringBuff, "B") << ((i & 3) << 3)
            sHashB &= 0xFFFFFFFF
            length -= 1
        for i in range(min(length, 4)):
            sHashA += ReadType(stringBuff, "B") << ((i & 3) << 3)
            sHashA &= 0xFFFFFFFF
            length -= 1

        a = (sHashC - sHashA + 0x100000000) ^ ROL4(sHashA, 4)
        a1 = sHashB + sHashA
        b = (sHashB - a + 0x100000000) ^ ROL4(a, 6)
        b1 = a1 + a
        c = (a1 - b + 0x100000000) ^ ROL4(b, 8)
        c1 = b1 + b
        d = (b1 - c + 0x100000000) ^ ROL4(c, 16)
        d1 = c1 + c
        e = (c1 - d + 0x100000000) ^ ROR4(d, 13)
        hashC = d1 + d
        hashA = (d1 - e + 0x100000000) ^ ROL4(e, 4)
        hashB = hashC + e

    if length <= 12:
        for i in range(min(length, 4)):
            hashC += ReadType(stringBuff, "B") << ((i & 3) << 3)
            hashC &= 0xFFFFFFFF
            length -= 1
        for i in range(min(length, 4)):
            hashB += ReadType(stringBuff, "B") << ((i & 3) << 3)
            hashB &= 0xFFFFFFFF
            length -= 1
        for i in range(min(length, 4)):
            hashA += ReadType(stringBuff, "B") << ((i & 3) << 3)
            hashA &= 0xFFFFFFFF
            length -= 1

    # Finish
    a = (hashB ^ hashA) - ROL4(hashB, 14) + 0x100000000
    a &= 0xFFFFFFFF
    b = (hashC ^ a) - ROL4(a, 11) + 0x100000000
    b &= 0xFFFFFFFF
    c = (b ^ hashB) - ROR4(b, 7) + 0x100000000
    c &= 0xFFFFFFFF
    d = (c ^ a) - ROL4(c, 16) + 0x100000000
    d &= 0xFFFFFFFF
    e = (((b ^ d) - ROL4(d, 4) + 0x100000000) ^ c) - ROL4((b ^ d) - ROL4(d, 4) + 0x100000000, 14) + 0x100000000
    e &= 0xFFFFFFFF
    f = ((e ^ d) - ROR4(e, 8)) + 0x100000000
    f &= 0xFFFFFFFF
    return f

class RSDK_SceneEditorMetadata:
    def __init__(self, file = None):
        self.UnusedByte1 = 0
        self.BackgroundColor1 = 0xFFFFFFFF
        self.BackgroundColor2 = 0xFFCCCCCC
        self.UnknownBytes = bytearray([ 0x1, 0x1, 0x4, 0x0, 0x1, 0x4, 0x0 ])
        self.UnknownString = ""
        self.UnusedByte2 = 0
        if file != None:
            self.Read(file)
    def Read(self, file):
        self.UnusedByte1 = ReadType(file, "B")
        self.BackgroundColor1 = ReadType(file, "I")
        self.BackgroundColor2 = ReadType(file, "I")
        self.UnknownBytes = file.read(7)
        self.UnknownString = ReadRSDKString(file)
        self.UnusedByte2 = ReadType(file, "B")
    def Write(self, file):
        WriteType(file, "B", self.UnusedByte1)
        WriteType(file, "I", self.BackgroundColor1)
        WriteType(file, "I", self.BackgroundColor2)
        file.write(self.UnknownBytes)
        WriteRSDKString(file, self.UnknownString)
        WriteType(file, "B", self.UnusedByte2)
class RSDK_ScrollInfo:
    def __init__(self, file = None):
        self.RelativeSpeed = 0x0100
        self.ConstantSpeed = 0x0000
        self.Behavior = 0
        self.DrawLayer = 0
        if file != None:
            self.Read(file)
    def Read(self, file):
        pack = struct.unpack("HHBB", file.read(0x6))
        self.RelativeSpeed = pack[0]
        self.ConstantSpeed = pack[1]
        self.Behavior = pack[2]
        self.DrawLayer = pack[3]
    def Write(self, file):
        file.write(struct.pack("HHBB", self.RelativeSpeed, self.ConstantSpeed, self.Behavior, self.DrawLayer))
class RSDK_SceneLayer:
    def __init__(self, width = 1, height = 1, file = None):
        self.UnusedByte1 = 0
        self.Name = "Empty Layer"
        self.Behaviour = 0
        self.DrawFlag = 0
        self.Width = width
        self.Height = height
        self.RelativeSpeed = 0x0100
        self.ConstantSpeed = 0x0000
        self.ScrollingInfo = [ RSDK_ScrollInfo() ]
        self.ScrollingIndexes = [ 0 ] * (self.Height * 16)
        self.Tiles = [[0xFFFF] * self.Height for i in range(self.Width)]
        if file != None:
            self.Read(file)
    def Read(self, file):
        self.UnusedByte1 = ReadType(file, "B")

        self.Name = ReadRSDKString(file)

        pack = struct.unpack("BBHHhhH", file.read(0xC))
        self.Behaviour = pack[0];
        self.DrawFlag = pack[1];
        self.Width = pack[2];
        self.Height = pack[3];
        self.RelativeSpeed = pack[4];
        self.ConstantSpeed = pack[5];

        self.ScrollingInfo = [None] * pack[6];
        for i in range(len(self.ScrollingInfo)):
            self.ScrollingInfo[i] = RSDK_ScrollInfo(file)

        self.ScrollingIndexes = ReadCompressed(file, "B")

        tiles = ReadCompressed(file, "H")
        self.Tiles = [[0xFFFF] * self.Height for i in range(self.Width)]
        for i in range(len(tiles)):
            self.Tiles[i % self.Width][i / self.Width] = tiles[i]
    def Write(self, file):
        WriteType(file, "B", self.UnusedByte1)

        WriteRSDKString(file, self.Name)

        file.write(struct.pack("BBHHhhH", self.Behaviour, self.DrawFlag, self.Width, self.Height, self.RelativeSpeed, self.ConstantSpeed, len(self.ScrollingInfo)))
        for i in range(len(self.ScrollingInfo)):
            self.ScrollingInfo[i].Write(file)

        WriteCompressed(file, "B", self.ScrollingIndexes)

        tiles = [0xFFFF] * self.Height * self.Width
        for i in range(len(tiles)):
            tiles[i] = self.Tiles[int(i % self.Width)][int(i / self.Width)]
        WriteCompressed(file, "H", tiles)

class RSDK_ObjectProperty:
    def __init__(self, file = None):
        self.Name = ""
        self.Hash = bytearray([ 0 ] * 16)
        self.Type = 0
        if file != None:
            self.Read(file)
    def Read(self, file):
        self.Hash = file.read(0x10)
        pack = struct.unpack("B", file.read(0x1))
        self.Type = pack[0]
    def Write(self, file):
        if self.Name == "":
            file.write(struct.pack("16sB", self.Hash, self.Type))
        else:
            m = hashlib.md5()
            m.update(self.Name.encode("utf8"))
            file.write(struct.pack("16sB", m.digest(), self.Type))
class RSDK_ObjectEntity:
    def __init__(self, pclass, file = None):
        self.SlotID = 0
        self.X = 0
        self.Y = 0
        self.Class = pclass
        self.Values = [0] * len(self.Class.Properties)
        if file != None:
            self.Read(file)
    def Read(self, file):
        pack = struct.unpack("HII", file.read(0xA))
        self.SlotID = pack[0]
        self.X = pack[1]
        self.Y = pack[2]

        argTypes = {
            0: "B",
            1: "H",
            2: "I",
            3: "b",
            4: "h",
            5: "i",
            6: "i",
            7: "I",
            11: "I",
        }

        for a in range(1, len(self.Class.Properties)):
            type = self.Class.Properties[a].Type
            if type == 8:
                str = ""
                len = ReadType(file, "H")
                for s in range(len):
                    str += "%c" % ReadType(file, "H")
                self.Values[a] = str
            elif type == 9:
                self.Values[a] = [ ReadType(file, "I"), ReadType(file, "I") ]
            else:
                self.Values[a] = ReadType(file, argTypes[a])
    def Write(self, file):
        file.write(struct.pack("=HII", self.SlotID, self.X, self.Y))

        argTypes = {
            0: "=B",
            1: "=H",
            2: "=I",
            3: "=b",
            4: "=h",
            5: "=i",
            6: "=i",
            7: "=I",
            11: "=I",
        }

        for a in range(1, len(self.Class.Properties)):
            type = self.Class.Properties[a].Type
            if type == 8:
                WriteType(file, "=H", len(self.Values[a]))
                for s in range(len(self.Values[a])):
                    WriteType(file, "=H", self.Values[a][s])
            elif type == 9:
                WriteType(file, "=I", self.Values[a][0])
                WriteType(file, "=I", self.Values[a][1])
            else:
                WriteType(file, argTypes[type], self.Values[a])
class RSDK_SceneClass:
    def __init__(self, file = None):
        self.Hash = bytearray([ 0 ] * 16)
        self.Properties = [ RSDK_ObjectProperty() ]
        self.Properties[0].Type = 8; # Position
        self.Entities = []
        if file != None:
            self.Read(file)
    def Read(self, file):
        self.Hash = file.read(0x10)

        self.Properties = [ None ] * ReadType(file, "B")
        # Position
        self.Properties[0] = RSDK_ObjectProperty()
        self.Properties[0].Type = 8;
        for a in range(1, len(self.Properties)):
            self.Properties[a] = RSDK_ObjectProperty(file)

        self.Entities = [ None ] * ReadType(file, "H")
        for a in range(0, len(self.Entities)):
            self.Entities[a] = RSDK_ObjectEntity(self, file)
    def Write(self, file):
        file.write(self.Hash)

        WriteType(file, "B", len(self.Properties))
        for a in range(1, len(self.Properties)):
            self.Properties[a].Write(file)

        WriteType(file, "H", len(self.Entities))
        for a in range(0, len(self.Entities)):
            self.Entities[a].Write(file)

    def AddProperty(self, type, name):
        property = RSDK_ObjectProperty()
        property.Name = name
        property.Type = type
        self.Properties.append(property)
        return property
    def AddEntity(self, x, y):
        entity = RSDK_ObjectEntity(self)
        entity.X = x
        entity.Y = y
        self.Entities.append(entity)
        return entity

class RSDK_Scene:
    def __init__(self, file = None):
        self.Magic = 0x4E4353
        self.EditorMetadata = RSDK_SceneEditorMetadata()
        self.Layers = []
        self.Classes = []

        self.ClassMap = {}
        if file != None:
            self.Read(file)
    def Read(self, file):
        self.Magic = ReadType(file, "I")

        self.EditorMetadata = RSDK_SceneEditorMetadata(file)

        self.Layers = [ None ] * ReadType(file, "B")
        for i in range(len(self.Layers)):
            self.Layers[i] = RSDK_SceneLayer(file)

        self.Classes = [ None ] * ReadType(file, "B")
        for i in range(len(self.Classes)):
            self.Classes[i] = RSDK_SceneClass(file)
    def Write(self, file):
        WriteType(file, "I", self.Magic)

        self.EditorMetadata.Write(file)

        WriteType(file, "B", len(self.Layers))
        for i in range(len(self.Layers)):
            self.Layers[i].Write(file)

        print("Object Definitions: 0x%X" % (file.tell()))

        WriteType(file, "B", len(self.Classes))
        for i in range(len(self.Classes)):
            self.Classes[i].Write(file)

    def GetClass(self, name):
        # Add class if it doesn't exist
        if not name in self.ClassMap:
            scnClass = RSDK_SceneClass()
            # Hash name
            m = hashlib.md5()
            m.update(name.encode("utf8"))
            scnClass.Hash = m.digest()
            # Add class to list and map
            self.Classes.append(scnClass)
            self.ClassMap[name] = scnClass
        return self.ClassMap[name]
    def AutoAdjustSlotIDs(self):
        slotID = 0
        for i in range(len(self.Classes)):
            classE = self.Classes[i]
            for a in range(len(classE.Entities)):
                classE.Entities[a].SlotID = slotID
                slotID += 1

class RSDK_PaletteColor:
    def __init__(self, file = None):
        self.RGB = 0x000000
        if file != None:
            self.Read(file)
    def Read(self, file):
        pack = struct.unpack("=BBB", file.read(3))
        self.RGB = pack[0] | pack[1] << 8 | pack[2] << 16
    def Write(self, file):
        file.write(struct.pack("=BBB", self.RGB & 0xFF, (self.RGB >> 8) & 0xFF, (self.RGB >> 16) & 0xFF))
class RSDK_Palette:
    def __init__(self, file = None):
        self.Colors = [ None ] * 16
        for i in range(16):
            self.Colors[i] = [ None ] * 16
            for j in range(16):
                self.Colors[i][j] = RSDK_PaletteColor()
        if file != None:
            self.Read(file)
    def Read(self, file):
        palette_bitmask = ReadType(file, "=H")
        for i in range(16):
            if (palette_bitmask & (1 << i)) != 0:
                self.Colors[i] = [ None ] * 16
                for j in range(16):
                    self.Colors[i][j] = RSDK_PaletteColor(file)
            else:
                self.Colors[i] = None
    def Write(self, file):
        palette_bitmask = 0
        for i in range(16):
            if self.Colors[i] != None:
                palette_bitmask |= 1 << i
        WriteType(file, "=H", palette_bitmask)

        for i in range(16):
            if self.Colors[i] != None:
                for j in range(16):
                    self.Colors[i][j].Write(file)
class RSDK_WAVConfiguration:
    def __init__(self, file = None):
        self.Name = ""
        self.MaxConcurrentPlay = 0xFF
        if file != None:
            self.Read(file)
    def Read(self, file):
        self.Name = ReadRSDKString(file)
        self.MaxConcurrentPlay = ReadType(file, "=B")
    def Write(self, file):
        WriteRSDKString(file, self.Name)
        WriteType(file, "=B", self.MaxConcurrentPlay)
class RSDK_StageConfig:
    def __init__(self, file = None):
        self.Magic = 0x474643
        self.LoadGlobalObjects = False
        self.ClassNames = []
        self.Palettes = [ None ] * 8
        for i in range(len(self.Palettes)):
            self.Palettes[i] = RSDK_Palette()
        self.WAVConfigs = []
        if file != None:
            self.Read(file)
    def Read(self, file):
        self.Magic = ReadType(file, "I")
        self.LoadGlobalObjects = ReadType(file, "B") != 0

        self.ClassNames = [ "" ] * ReadType(file, "B")
        for i in range(len(self.ClassNames)):
            self.ClassNames[i] = ReadRSDKString(file)

        for i in range(8):
            self.Palettes[i] = RSDK_Palette(file)

        self.WAVConfigs = [ None ] * ReadType(file, "B")
        for i in range(len(self.WAVConfigs)):
            self.WAVConfigs[i] = RSDK_WAVConfiguration(file)
    def Write(self, file):
        WriteType(file, "I", self.Magic)
        WriteType(file, "B", self.LoadGlobalObjects)

        WriteType(file, "B", len(self.ClassNames))
        for i in range(len(self.ClassNames)):
            WriteRSDKString(file, self.ClassNames[i])

        for i in range(8):
            self.Palettes[i].Write(file)

        WriteType(file, "B", len(self.WAVConfigs))
        for i in range(len(self.WAVConfigs)):
            self.WAVConfigs[i].Write(file)

class RSDK_CollisionMask:
    def __init__(self, file = None):
        self.Collision = bytearray([0] * 16)
        self.HasCollision = bytearray([0] * 16)
        self.IsCeiling = False
        self.TopAngle = 0x00
        self.LeftAngle = 0xC0
        self.RightAngle = 0x40
        self.BottomAngle = 0x80
        self.Behavior = 0
        if file != None:
            self.Read(file)
    def Read(self, file):
        pack = struct.unpack("=16s16sBBBBBB", file.read(0x26))
        self.Collision = pack[0]
        self.HasCollision = pack[1]
        self.IsCeiling = pack[2]
        self.TopAngle = pack[3]
        self.LeftAngle = pack[4]
        self.RightAngle = pack[5]
        self.BottomAngle = pack[6]
        self.Behavior = pack[7]
    def Write(self, file):
        file.write(struct.pack("=16s16sBBBBBB", self.Collision, self.HasCollision, self.IsCeiling, self.TopAngle, self.LeftAngle, self.RightAngle, self.BottomAngle, self.Behavior))
class RSDK_TileConfig:
    def __init__(self, file = None):
        self.Magic = 0x4C4954
        self.CollisionPath1 = [ None ] * 0x400
        self.CollisionPath2 = [ None ] * 0x400
        for i in range(0x400):
            self.CollisionPath1[i] = RSDK_CollisionMask()
            self.CollisionPath2[i] = RSDK_CollisionMask()
        if file != None:
            self.Read(file)
    def Read(self, file):
        self.Magic = ReadType(file, "I")

        compressedSize = ReadType(file, "I") - 4
        decompressedSize = ReadTypeBE(file, "I")
        buff = file.read(compressedSize)
        buff = zlib.decompress(buff)
        buff = io.BytesIO(buff)

        for i in range(len(self.CollisionPath1)):
            self.CollisionPath1[i] = RSDK_CollisionMask(buff)
        for i in range(len(self.CollisionPath2)):
            self.CollisionPath2[i] = RSDK_CollisionMask(buff)
    def Write(self, file):
        WriteType(file, "I", self.Magic)

        buff = io.BytesIO()

        for i in range(len(self.CollisionPath1)):
            self.CollisionPath1[i].Write(buff)
        for i in range(len(self.CollisionPath2)):
            self.CollisionPath2[i].Write(buff)

        decompressedSize = (buff.tell()) * 0x26
        buff.seek(0)

        buffArrComp = zlib.compress(buff.read())
        compressedSize = len(buffArrComp)
        WriteType(file, "I", compressedSize + 4)
        WriteTypeBE(file, "I", decompressedSize)
        file.write(buffArrComp)

class LTBClass:
    def __init__(self, ltb_file):
        if ltb_file.suffix == '.ltb':
            self.unpack(ltb_file)
        else:
            _exit("Error: This is not a valid .LTB file!")

    def unpack(self, ltb_file):
        self.file = open(ltb_file, 'rb')

        file = self.file
        # path_hash = unpack(file, 4)

        # fpath = "levels/core/plainsOfPassage.ltb"
        # print("File Hash: 0x%08X" % YCG_Hash(fpath, len(fpath), 123456789))

        self.ltb_start = ltb_start = 0x10
        file.seek(ltb_start)

        layerFormatHeader = struct.unpack("IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII", file.read(0x90))

        unk_0x00 = layerFormatHeader[0]
        unk_0x04 = layerFormatHeader[1]
        tileSize = layerFormatHeader[2]
        chunkWidth = layerFormatHeader[3]
        chunkHeight = layerFormatHeader[4]
        layerInfoCount = layerFormatHeader[5]
        layerInfoOffset = layerFormatHeader[6]
        vertexBufferInfoCount = layerFormatHeader[9]
        vertexBufferInfoOffset = layerFormatHeader[10]
        textureFormatInfoCount = layerFormatHeader[13]
        textureFormatInfoOffset = layerFormatHeader[14]
        chunkCount = layerFormatHeader[17]
        chunkOffset = layerFormatHeader[18]
        tileBufferCount = layerFormatHeader[21]
        tileBufferOffset = layerFormatHeader[22]
        uvPointCount = layerFormatHeader[25]
        uvPointOffset = layerFormatHeader[26]
        staticVertexDataCount = layerFormatHeader[29]
        staticVertexDataOffset = layerFormatHeader[30]
        attachedFileCount = layerFormatHeader[33]
        attachedFileOffset = layerFormatHeader[34]

        print("LayerFormat Header:")
        print("-------------------")
        print("Tile Size: %d" % tileSize)
        print("Layer Info Count: %d" % layerInfoCount)
        print("Layer Info Offset: 0x%X" % layerInfoOffset)
        print("VertexBufferInfo Count: %d" % vertexBufferInfoCount)
        print("VertexBufferInfo Offset: 0x%X" % vertexBufferInfoOffset)
        print("Texture Info Count: %d" % textureFormatInfoCount)
        print("Texture Info Offset: 0x%X" % textureFormatInfoOffset)
        print("Chunk Tile Buffer Start Count: %d" % chunkCount)
        print("Chunk Tile Buffer Start Offset: 0x%X" % chunkOffset)
        print("Tile Buffer Count: %d" % tileBufferCount)
        print("Tile Buffer Offset: 0x%X" % tileBufferOffset)
        print("UV Count: %d" % uvPointCount)
        print("UV Offset: 0x%X" % uvPointOffset)
        print("Static Vertex Data Count: %d" % staticVertexDataCount)
        print("Static Vertex Data Offset: 0x%X" % staticVertexDataOffset)
        print("Attached File Offset Count: %d" % attachedFileCount)
        print("Attached File Offset List Offset: 0x%X" % attachedFileOffset)
        print("")

        # Layer Info List
        self.layerInfo = namedtuple("LayerInfo", "name nameHash unk1 unk2 cameraMultX unk3 cameraMultY unk4 unk5 unk6 unkI7 unkI8 unkI9 vertexBufferInfoIndex isUsingStaticVertexBuffer unkI10 chunkXCount chunkYCount chunkIDStart offsetX offsetY startX startY endX endY")
        self.layerInfoList = [None] * layerInfoCount

        file.seek(ltb_start + layerInfoOffset)
        for i in range(layerInfoCount):
            self.layerInfoList[i] = self.layerInfo._make(struct.unpack("32sIffffffffIIIIIIIIIffIIII", file.read(0x80)))

        # Vertex Buffer Info List
        self.vertexBufferInfo = namedtuple("VertexBufferInfo", "unk1 textureIndex vertexCount unk4 unk5")
        self.vertexBufferInfoList = [None] * vertexBufferInfoCount

        file.seek(ltb_start + vertexBufferInfoOffset)
        for i in range(vertexBufferInfoCount):
            self.vertexBufferInfoList[i] = self.vertexBufferInfo._make(struct.unpack("IIIII", file.read(0x14)))

        # Texture Format Info
        self.textureFormatInfo = namedtuple("TextureFormatInfo", "unk1 isCompressed width height unk2 unk3 unk4 unk5 unk6 unk7 unk8 unk9 unk10 unk11 unk12 unk13 unk14 unk15 size")
        self.textureFormatInfoList = [None] * textureFormatInfoCount

        file.seek(ltb_start + textureFormatInfoOffset)
        for i in range(textureFormatInfoCount):
            self.textureFormatInfoList[i] = self.textureFormatInfo._make(struct.unpack("IIIIfIiiiiiiiiiiiiI", file.read(0x4C)))

        # Chunk Infos
        self.chunkInfo = namedtuple("ChunkInfo", "tileBufferStart")
        self.chunkInfoList = [None] * chunkCount

        file.seek(ltb_start + chunkOffset)
        for i in range(chunkCount):
            self.chunkInfoList[i] = self.chunkInfo._make(struct.unpack("I", file.read(0x4)))

        # tileBuffer
        self.tileBufferList = [0] * tileBufferCount

        file.seek(ltb_start + tileBufferOffset)
        for i in range(tileBufferCount):
            self.tileBufferList[i] = struct.unpack("H", file.read(0x2))[0]

        # self.uvPointList
        self.uvPoint = namedtuple("UVPoint", "u1 v1 u2 v2")
        self.uvPointList = [None] * uvPointCount

        file.seek(ltb_start + uvPointOffset)
        for i in range(int(uvPointCount / 2)):
            self.uvPointList[i] = self.uvPoint._make(struct.unpack("ffff", file.read(0x10)))

        # Static Vertex Data List
        self.staticVertexData = namedtuple("StaticVertexData", "x y z u v")
        self.staticVertexDataList = [None] * staticVertexDataCount

        file.seek(ltb_start + staticVertexDataOffset)
        for i in range(staticVertexDataCount):
            self.staticVertexDataList[i] = self.staticVertexData._make(struct.unpack("fffff", file.read(0x14)))

        # Attached File Offset List
        self.attachedFileList = [0] * attachedFileCount

        file.seek(ltb_start + attachedFileOffset)
        for i in range(attachedFileCount):
            self.attachedFileList[i] = struct.unpack("Q", file.read(0x8))[0]

class LVBClass:
    def __init__(self, lvb_file):
        if lvb_file.suffix == '.lvb':
            self.unpack(lvb_file)
        else:
            _exit("Error: This is not a valid .LVB file!")

    def unpack(self, ltb_file):
        self.file = open(ltb_file, 'rb')

        file = self.file
        # path_hash = unpack(file, 4)

        self.lvb_start = lvb_start = 0x10
        file.seek(lvb_start)

        # header = struct.unpack("IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII", file.read(0x150))
        header = struct.unpack("IIQIIQIIQIIQIIQIIQIIQ", file.read(0x70))

        unk_Value_0x00 = header[0]
        objectPropertyCountListCount = header[1]
        objectPropertyCountListOffset = header[2]
        objectInfoCount = header[3]
        unk_Count_0x10 = header[4]
        objectInfoListOffset = header[5]
        unk_Value_0x20 = header[6]
        rectangleBatchCount = header[7]
        rectangleBatchOffset = header[8]
        unk_Value_0x30 = header[9]
        rectListCount = header[10]
        rectListOffset = header[11]
        unk_Value_0x40 = header[12]
        propertyValueSetListCount = header[13]
        propertyValueSetListOffset = header[14]
        unk_Value_0x50 = header[15]
        unk_Count_0x50 = header[16]
        unk_Offset_0x50 = header[17]
        unk_Value_0x60 = header[18]
        unk_Count_0x60 = header[19]
        unk_Offset_0x60 = header[20]

        print("LayerObject Header:")
        print("-------------------")
        print("unk_Value_0x00: %d" % unk_Value_0x00)
        print("objectPropertyCountListCount: 0x%X" % objectPropertyCountListCount)
        print("objectPropertyCountListOffset: 0x%X" % objectPropertyCountListOffset)
        print("")
        print("objectInfoCount: 0x%X" % objectInfoCount)
        print("unk_Count_0x10: 0x%X" % unk_Count_0x10)
        print("objectInfoListOffset: 0x%X" % objectInfoListOffset)
        print("")
        print("rectangleBatchCount: 0x%X" % rectangleBatchCount)
        print("rectangleBatchOffset: 0x%X" % rectangleBatchOffset)
        print("")
        print("rectListCount: 0x%X" % rectListCount)
        print("rectListOffset: 0x%X" % rectListOffset)
        print("")
        print("unk_Value_0x40: %d" % unk_Value_0x40)
        print("Property Value Count: 0x%X" % propertyValueSetListCount)
        print("Property Value List Offset: 0x%X" % propertyValueSetListOffset)
        print("")
        print("unk_Count_0x50: 0x%X" % unk_Count_0x50)
        print("unk_Offset_0x50: 0x%X" % unk_Offset_0x50)
        print("")
        print("String List Size: %d" % unk_Count_0x60)
        print("String List Offset: 0x%X" % unk_Offset_0x60)
        print("")

        ### Property Count Map
        # Input:    ObjectID
        # Output:   Property Count
        self.objectPropertyCountMap = { }
        file.seek(lvb_start + objectPropertyCountListOffset)
        for i in range(objectPropertyCountListCount):
            packed = struct.unpack("II", file.read(0x8))
            self.objectPropertyCountMap[packed[0]] = packed[1]

        ### Object Infos
        self.objectInfo = namedtuple("ObjectInfo", "unkHash layerNameHash x y scalex scaley isUnk6 objectID unk7 gID propertyCount propertyIndexStart unk11")
        self.objectInfoList = [ None ] * objectInfoCount

        file.seek(lvb_start + objectInfoListOffset)
        for i in range(len(self.objectInfoList)):
            self.objectInfoList[i] = self.objectInfo._make(struct.unpack("IIffffIHHIIII", file.read(0x30)))
            object = self.objectInfoList[i]
            # print("pos (%f %f) isUnk6 %X unk7 %X gID %X propertyCount %X propertyIndexStart %X unk11 %X" % (object.x, object.y, object.isUnk6, object.unk7, object.gID, object.propertyCount, object.propertyIndexStart, object.unk11))

        ### Rectangle Batches
        self.rectangleBatch = namedtuple("RectangleBatch", "hash flag flag2 count start")
        self.rectangleBatchList = [ None ] * rectangleBatchCount
        file.seek(lvb_start + rectangleBatchOffset)
        for i in range(rectangleBatchCount):
            self.rectangleBatchList[i] = self.rectangleBatch._make(struct.unpack("IIIII", file.read(0x14)))

        ### Rectangle Infos
        self.rectangleInfo = namedtuple("RectangleInfo", "x y width height isUnk id")
        self.rectangleInfoList = [ None ] * rectListCount
        file.seek(lvb_start + rectListOffset)
        for i in range(rectListCount):
            self.rectangleInfoList[i] = self.rectangleInfo._make(struct.unpack("IIIIIi", file.read(0x18)))

        ### Unique Property Value Sets
        self.propertyValueSet = namedtuple("UniquePropertyValueSet", "hash stringOffset")
        self.propertyValueSetList = [ None ] * propertyValueSetListCount
        file.seek(lvb_start + propertyValueSetListOffset)
        for i in range(propertyValueSetListCount):
            self.propertyValueSetList[i] = self.propertyValueSet._make(struct.unpack("II", file.read(0x8)))

        ### Paths
        print("Paths:")
        print("------")
        paths = [0] * unk_Count_0x50
        file.seek(lvb_start + unk_Offset_0x50)
        for i in range(len(paths)):
            paths[i] = struct.unpack("Q", file.read(0x8))[0]

        for i in range(len(paths) - 1):
            file.seek(lvb_start + paths[i])
            object = struct.unpack("I32sIfffIIIIIIIIIffffffffffffff", file.read(0x90))
            print("%s" % (object[1].decode("utf8").split("\0", 1)[0]))
            print("0x%08X %f %f %f" % (object[0x2], object[0x3], object[0x4], object[0x5]))
            print("0x%08X 0x%08X 0x%08X 0x%08X" % (object[0x6], object[0x7], object[0x8], object[0x9]))
            print("0x%08X 0x%08X 0x%08X 0x%08X" % (object[0xA], object[0xB], object[0xC], object[0xD]))
            print("0x%08X" % (object[0xE]))
            for v in range(4):
                print("%.2f %.2f %.2f" % (object[0xF + v * 3], object[0x10 + v * 3], object[0x11 + v * 3]))
            print("%.2f %.2f %.2f" % (object[0x1A], object[0x1B], object[0x1C]))
        #     # print("0x%08X %s 0x%08X %f" % (object[12], object[13].decode("utf8").split("\0", 1)[0], object[14], object[15]))
        #     # print("0x%08X 0x%08X 0x%08X 0x%08X" % (object[0x10], object[0x11], object[0x12], object[0x13]))
        #     # print("0x%08X 0x%08X 0x%08X 0x%08X" % (object[0x14], object[0x15], object[0x16], object[0x17]))
        #     # print("0x%08X 0x%08X 0x%08X 0x%08X" % (object[0x18], object[0x19], object[0x1A], object[0x1B]))
        #     # print("0x%08X" % (object[0x1C]))
            print("")
        # print("")

        ### Value strings
        self.valueStringListMap = { }
        file.seek(lvb_start + unk_Offset_0x60)
        start_pos = file.tell()
        while file.tell() < start_pos + unk_Count_0x60:
            pos = file.tell() - start_pos
            self.valueStringListMap[pos] = ReadString(file)

        return

def LTBandLVBtoRSDKScene(ltb, lvb, folder):
    wflz = WFLZ()
    paletteFileIndex = 0
    paletteColorCount = 0
    paletteColorABGRtoIndexMap = { }
    paletteColorIndexMaptoABGR = { }

    tilesIndexedByteArr = [0] * (0x10 * 0x4000)
    tilesCount = 0

    srcTileMargin = 1
    srcTilePadding = 2
    srcTileSize = 16
    srcTileCount = [ 0, 3, 401 ]
    srcTileStart = [ 0, 0, 3 ] # this should be filled automatically

    tilesSolidMap = { }

    parent_dir = Path(folder)
    parent_dir.mkdir(exist_ok=True)

    # Get starting palette
    if paletteFileIndex != -1:
        textureFormatInfo = ltb.textureFormatInfoList[paletteFileIndex]
        ltb.file.seek(ltb.ltb_start + ltb.attachedFileList[paletteFileIndex])
        byteArr = ltb.file.read(textureFormatInfo.size)
        for i in range(len(byteArr) >> 2):
            i <<= 2
            abgr = byteArr[i + 0] | byteArr[i + 1] << 8 | byteArr[i + 2] << 16 | byteArr[i + 3] << 24
            i >>= 2

            if abgr != 0xFF00FF00:
                paletteColorABGRtoIndexMap[abgr] = paletteColorCount
                paletteColorIndexMaptoABGR[paletteColorCount] = abgr
                print("color[%d] = 0x%X" % (paletteColorCount, abgr))
                paletteColorCount += 1

    # Add used colors to the palette & add tiles
    for i in range(len(ltb.textureFormatInfoList)):
        if i != paletteFileIndex:
            ltb.file.seek(ltb.ltb_start + ltb.attachedFileList[i])

            textureFormatInfo = ltb.textureFormatInfoList[i]
            if textureFormatInfo.isCompressed != 0:
                byteArr = wflz.decomp_file(ltb.file)
            else:
                byteArr = ltb.file.read(textureFormatInfo.size)

            bpp = len(byteArr) / (textureFormatInfo.width * textureFormatInfo.height)
            indexedByteArr = [0] * len(byteArr)
            if bpp == 4:
                for p in range(len(byteArr) >> 2):
                    p <<= 2
                    abgr = byteArr[p + 0] | byteArr[p + 1] << 8 | byteArr[p + 2] << 16 | byteArr[p + 3] << 24
                    p >>= 2

                    if abgr in paletteColorABGRtoIndexMap.keys():
                        indexedByteArr[p] = paletteColorABGRtoIndexMap[abgr]
                    else:
                        indexedByteArr[p] = paletteColorCount

                        paletteColorABGRtoIndexMap[abgr] = paletteColorCount
                        paletteColorIndexMaptoABGR[paletteColorCount] = abgr
                        print("color[%d] = 0x%X" % (paletteColorCount, abgr))
                        paletteColorCount += 1
            else:
                for p in range(len(byteArr)):
                    indexedByteArr[p] = byteArr[p] >> 3

            t = srcTileCount[i]
            if t > 0:
                srcTileCountW = int(textureFormatInfo.width / (srcTileSize + srcTilePadding))
                for tp in range(int(t * 16 * 16)):
                    srcInd = int(tp / 16 / 16)
                    tp += int(tilesCount * 16 * 16)
                    tpx = int(tp % 16)
                    tpy = int(tp / 16)
                    srcX = srcTileMargin + int(srcInd % srcTileCountW) * (srcTileSize + srcTilePadding) + tpx
                    srcY = srcTileMargin + int(srcInd / srcTileCountW) * (srcTileSize + srcTilePadding) + (tpy % 16)
                    tilesIndexedByteArr[tp] = indexedByteArr[srcX + srcY * textureFormatInfo.width]
                tilesCount += t

    # Add padding to palette
    for c in range(paletteColorCount, 256):
        paletteColorIndexMaptoABGR[paletteColorCount] = 0xFF7F00FF
        paletteColorCount += 1

    # Turn into paletteData
    paletteData = [0] * 0x300
    for c in range(paletteColorCount):
        ABGR = paletteColorIndexMaptoABGR[c]
        paletteData[c * 3 + 0] = (ABGR) & 0xFF
        paletteData[c * 3 + 1] = (ABGR >> 8) & 0xFF
        paletteData[c * 3 + 2] = (ABGR >> 16) & 0xFF

    # Replace transparent index with magenta
    paletteData[0] = 0xFF
    paletteData[1] = 0x00
    paletteData[2] = 0xFF

    # Output 16x16Tiles.gif
    image = Image.new("P", (0x10, 0x4000))
    image.putpalette(paletteData)
    image.putdata(tilesIndexedByteArr)
    image.save(folder + "/" + "16x16Tiles.gif")

    # Create Scene1.bin
    outputLayerMap = {
        "BG": 0,
        "MG3": 1,
        "MG2": 2,
        "MG1.5": 3,
        "MG1_TREES": 4,
        "BGWATERFALL": 5,
        "PF_BG_FORWATER": 6,
        "PF_BG": 6,
        "LADDER": 7,
        "LADDER_SHOVEL": 7,
        "PF": 7,
        "PF_SHOVEL": 7,
    }
    layerSizes = [
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
        [0, 0],
    ]

    # Tileize static vertex buffer
    columncount = 28
    tileBufferSVB = [[0] * 32 for i in range(32)]
    for i in range(len(ltb.staticVertexDataList) >> 2):
        # Z formation
        v1 = ltb.staticVertexDataList[i * 4 + 0]
        v2 = ltb.staticVertexDataList[i * 4 + 1]
        v3 = ltb.staticVertexDataList[i * 4 + 2]
        v4 = ltb.staticVertexDataList[i * 4 + 3]

        # Compare UVs to determine orientation
        flip_x = v1[3] > v2[3]
        flip_y = v1[4] > v2[4]

        mean_x = (v1[0] + v2[0] + v3[0] + v4[0]) / 4
        mean_y = (v1[1] + v2[1] + v3[1] + v4[1]) / 4

        x = mean_x / 0.1 + 240.0 # / 0.1, as this is undoes what game does internally
        y = mean_y / 0.1 + 160.0 # / 0.1, as this is undoes what game does internally
        z = v1[2]
        u = v1[3] * 512.0
        v = v1[4] * 512.0

        tile_x = math.floor(x / 16.0)
        tile_y = math.floor(y / 16.0)
        cell_x = math.floor(u / 18.0)
        cell_y = math.floor(v / 18.0)
        tileBufferSVB[tile_x][tile_y] = math.floor(cell_x + cell_y * columncount) + 1

    scene = RSDK_Scene()

    # Get max sizes for each layer
    for i in range(len(ltb.layerInfoList)):
        layer = ltb.layerInfoList[i]
        layerName = layer.name.decode("utf8").split('\0', 1)[0]
        if "_PLAGUE" in layerName:
            continue
        if layer.endX - layer.startX < -1:
            continue
        if layer.endY - layer.startY < -1:
            continue

        endX = layer.endX + 1
        endY = layer.endY + 1

        targetLayerIndex = outputLayerMap[layerName]
        if layerSizes[targetLayerIndex][0] < endX:
            layerSizes[targetLayerIndex][0] = endX
        if layerSizes[targetLayerIndex][1] < endY:
            layerSizes[targetLayerIndex][1] = endY

    # Set layers and sizes
    for i in range(8):
        if layerSizes[i][0] > 0 and layerSizes[i][1] > 0:
            sceneLayer = RSDK_SceneLayer(layerSizes[i][0], layerSizes[i][1])
            scene.Layers.append(sceneLayer)

    # Write layers to scene
    for i in range(len(ltb.layerInfoList)):
        layer = ltb.layerInfoList[i]
        layerName = layer.name.decode("utf8").split('\0', 1)[0]
        if not layerName in outputLayerMap.keys():
            continue
        if layer.endX - layer.startX < -1:
            continue
        if layer.endY - layer.startY < -1:
            continue

        targetLayerIndex = outputLayerMap[layerName]
        sceneLayer = scene.Layers[targetLayerIndex]
        sceneLayer.Name = layerName
        sceneLayer.ScrollingInfo[0].RelativeSpeed = int(layer.cameraMultX * 0x100)

        if layer.isUsingStaticVertexBuffer != 0:
            for ty in range(layer.endY - layer.startY + 1):
                for tx in range(layer.endX - layer.startX + 1):
                    tile = int(tileBufferSVB[tx][layer.endY - ty])
                    if tile != 0:
                        tile += srcTileStart[ltb.vertexBufferInfoList[layer.vertexBufferInfoIndex].textureIndex]
                        sceneLayer.Tiles[layer.startX + tx][layer.startY + ty] = tile - 1
        else:
            chunkStart = layer.chunkIDStart
            for cy in range(layer.chunkYCount):
                for cx in range(layer.chunkXCount):
                    chunkID = chunkStart + cx + cy * layer.chunkXCount
                    tileStart = ltb.chunkInfoList[chunkID].tileBufferStart
                    if tileStart > 0:
                        for ty in range(16):
                            for tx in range(16):
                                tiledata = ltb.tileBufferList[tileStart + tx + ty * 16]
                                isSolid = tiledata & 0x8000
                                flip_x = tiledata & 0x2000
                                flip_y = tiledata & 0x4000
                                tile_id = tiledata & 0xFFF

                                if layer.startX + cx * 16 + tx <= layer.endX and layer.startY + cy * 16 + ty <= layer.endY:
                                    tiled_out = tile_id

                                    if tile_id != 0:
                                        tiled_out += srcTileStart[ltb.vertexBufferInfoList[layer.vertexBufferInfoIndex].textureIndex]
                                        tiled_out -= 1

                                        tiled_out &= 0x3FF

                                        if isSolid != 0:
                                            if not tiled_out in tilesSolidMap.keys():
                                                tilesSolidMap[tiled_out] = True

                                        if flip_x != 0:
                                            tiled_out |= 0x400
                                        if flip_y != 0:
                                            tiled_out |= 0x800
                                        if isSolid != 0:
                                            tiled_out |= 0xF000

                                        sceneLayer.Tiles[layer.startX + cx * 16 + tx][layer.startY + cy * 16 + ty] = tiled_out

    # Write objects to scene
    objectNameDict = {
        1: "PlayerSK",
        # 3: "DirtBlockLarge",
        # 4: "DirtBlockSmall",
        # 11: "GemRed",
        # 12: "GemPink",
        # 13: "GemPile",
        # 14: "Platter",
        # 20: "Chest",
        # 25: "CheckpointUnbreakable",
        # 29: "PlatformBackForth",
        # 37: "Beeto",
        # 57: "Slime",
        # 46: "FrontGrass",
        # 72: "Note",
        # 106: "SwordSkeleton",
        # 112: "GemPileWall",
        # 132: "Skull",
        # 137: "GemSmall",
        # 147: "GreenDragon",
        # 150: "BossBlackKnightPlains",
        # 154: "Bubble",
        # 161: "BubbleDragon",
        # 162: "BreakableWall",
    }
    usedObjectClassDict = { }

    for i in range(len(lvb.objectInfoList)):
        object = lvb.objectInfoList[i]
        oID = object.objectID & 0xFFF
        if oID in objectNameDict.keys():
            oName = objectNameDict[oID]
            usedObjectClassDict[oName] = True

            subObjectID = 0

            if oName in scene.ClassMap:
                scnClass = scene.GetClass(oName)
            else:
                scnClass = scene.GetClass(oName)
                scnClass.AddProperty(0, "SubObjectID")

            entity = scnClass.AddEntity(int(object.x * 0x10000), int(object.y * 0x10000))
            entity.Values[1] = subObjectID

    scene.AutoAdjustSlotIDs()
    scene.Write(open(folder + "/" + "Scene1.bin", "wb"))

    # Create StageConfig
    stageConfig = RSDK_StageConfig()

    # Copy over class names
    stageConfig.ClassNames = []
    for i in usedObjectClassDict.keys():
        stageConfig.ClassNames.append(i)

    # Copy over palette
    for i in range(paletteColorCount):
        stageConfig.Palettes[0].Colors[int(i / 16)][int(i % 16)].RGB = paletteColorIndexMaptoABGR[i] & 0xFFFFFF

    # Write StageConfig
    stageConfig.Write(open(folder + "/" + "StageConfig.bin", "wb"))

    # Create TileConfig
    tileConfig = RSDK_TileConfig()

    # Give only solid tiles collision
    for i in tilesSolidMap.keys():
        tileConfig.CollisionPath1[i].HasCollision = bytearray([1] * 16)
        tileConfig.CollisionPath2[i].HasCollision = bytearray([1] * 16)

    # Write TileConfig
    tileConfig.Write(open(folder + "/" + "TileConfig.bin", "wb"))
    return

def LTBandLVBtoTiled(ltb, lvb):
    # Player pos 90.4 -468.99

    objectNameDict = {
        1: "Player",
        3: "DirtBlockLarge",
        4: "DirtBlockSmall",
        11: "GemRed",
        12: "GemPink",
        13: "GemPile",
        14: "Platter",
        20: "Chest",
        25: "CheckpointUnbreakable",
        29: "PlatformBackForth",
        37: "Beeto",
        57: "Slime",
        46: "FrontGrass",
        72: "Note",
        104: "FishingPit",
        106: "SwordSkeleton",
        112: "GemPileWall",
        132: "Skull",
        137: "GemSmall",
        147: "GreenDragon",
        150: "BossBlackKnightPlains",
        154: "Bubble",
        161: "BubbleDragon",
        162: "BreakableWall",
        196: "PlagueCoin",
        215: "PlagueUnknown1"
    }
    parameterMap = { }
    parameterList = [
        "COLLISION0",
        "COLLISION1",
        "COLLISION2",
        "COLLISION3",
        "COLLISION4",
        "COLLISION5",
        "COLLISION6",
        "COLLISION7",
        "COLLISION8",
        "COLLISION9",
        "collision_hard_shop",
        "ladder",
        "ladder_shovel",
        "ladder_SHOVEL",
        "ladder_PLAGUE",
        "LADDER",
        "LADDER_SHOVEL",
        "LADDER_PLAGUE",
        "collision_hard_attac",
        "collision_soft",
        "collision_hard4",
        "collision_hard3",
        "collision_hard_SHIP",
        "collision_hardLoweri",
        "collision_hardRising",
        "collision_hard1",
        "collision_hard_break",
        "collision_hard_l",
        "collision_hard_r",
        "no_bounce2",
        "collision_hard_2",
        "no_climb_l",
        "no_climb_r",
        "water2",
        "collision_hard2",
        "ladder_hidden",
        "death_pit",
        "death_pit_shovel",
        "death_pit_PLAGUE",
        "collision_hard_hat",
        "collision_soft_hat",
        "death_pit_hole",
        "collision_hard_hole",
        "collision_hard_door",
        "collision_soft_hazard",
        "collision_hard_hazard",
        "PF_HAZARD",
        "BGWATERFALL_HAZARD",
        "PF_SOFT_HAZARD",
        "collision_hard_hazard",
        "no_bounce",
        "ladder_2",
        "collision_hard_luan",
        "collision_hard_k",
        "collision_hard_boss",
        "death_lava",
        "collision_hard_windo",
        "no_climb",
        "collision_hard_castl",
        "collision_hard_break_SPECTER",
        "waterFG",
        "PF",
        "ladder",
        "TORCH",
        "specterRoom1",
        "specterRoom2",
        "specterRoomback",
        "PF_BG",
        "deepWater",
        "deepWaterBack",
        "fog",
        "mg1",
        "mg2",
        "BG",
        "PF_ATTACK",
        "PF_ATTACK_FANCY",
        "PF_ATTACK_FANCY2",
        "PF",
        "PF_fancy",
        "PF_fancy2",
        "SOFT PLATFORMS",
        "SOFT PLATFORMS_FANCY",
        "SOFT PLATFORMS_FANCY2",
        "PF_BG0",
        "PF_BG0_Fancy",
        "PF_BG0_Fancy2",
        "PF_BG",
        "PF_BG_fancy",
        "PF_BG_fancy2",

        "COLLISION",
        "BOUNDS",
        "SCREEN",
        "SCREEN_BOUND",
        "SCREEN_BOUNDS",

        # Strings
        "CONTENTSSPAWNTYPE",
        "animSequence",
        "INDEX",
        "TRIGGER_RANGE_X",
        "VEL_RISE",
        "VEL_FALL",
        "TIME_FALL_WAIT",
        "COOLDOWN",
        "SPAWN_TREASURE",
        "DISTANCE_Y",
        "DOWN",
        "SPEED_RIDING",
        "SPAWNTIME",
        "TRIGGER_RANGE_Y",
        "TRIGGER_TIME",
        "BOMB_SPEED",
        "TRIGGER_RANGE_OFFSET",
        "SPEED",
        "DESTROY",
        "CHEST",
        "ROPE",
        "animResource",
        "paletteResource",
        "palette",
        "animPlayrate",
        "paletteLayer",
        "paletteShiftDisable",
        "LEFT",
        "RIGHT",
        "postBattle",
        "behavior",
        "VEL_Y",
        "WAIT_TIME",
        "WAIT_INTRO",
        "PIT",
        "UNDO_SHAKE",
        "CEILING_CAP_PHYSICS",
        "CEILING",
        "NO_WALLS",
        "EXIT_LEFT",
        "STAYHIGH",
        "SAFESCREEN",
        "CRUSH",
        "WAIT_MOVINGROOM",
        "WAIT_BIGBUG",
        "SAFEABOVE",
        "SAFESIDE",
        "Extend",
        "SHOTDIR",
        "TIME",
        "TIME_OFFSET",
        "VEL_X",
        "PHYSICS",
        "LAYER",
        "NOEXIT",
        "TOP",
        "WAIT_FOR_ELEVATOR",
        "DISTANCE",
        "PLAYERNUM",
        "bike",
        "battle",
        "rappel",
        "WAIT_OFFSCREEN",
        "RANGE_X",
        "JUMP_Y",
        "PLAYER_TIMER",
        "SPEED_MIN",
        "SPEED_MAX",
        "JUMP_MIN",
        "JUMP_MAX",
        "IGNORE_EDGE",
        "JUMP",
        "layer",
        "TYPE",
        "NOCONVEYER",
        "NOEXPLOSION",
        "HOPMUCH",
        "PLATFORM",
        "respawn",
        "LIT",
        "riseY",
        "forceCamera",
        "warpTo",
        "PATH",
        "ANTIC",
        "VISIBLE",
        "SHOT_TIME",
        "HOLD_TIME",
        "RETURN_TIME",
        "CORE",
        "PUSH_RIGHT",
        "PUSH_LEFT",
        "PUSH_DOWN",
        "PUSH_UP",
        "SHOT_SPEED",
        "RETURN_SPEED",
        "SIZE",
        "PIECE",
        "WALL",
        "CONTROLLER_CHECK",
        "TIME_MOVE",
        "SHAKE_START",
        "SHAKE_END",
        "DEFAULT",
        "START",
        "SNAP_START",
        "type",
        "region",
        "HEIGHT",
        "WIDTH",
        "TIME_CYCLE",
        "PATROL_X",
        "PATROL_TIME",
        "HALFTILE",
        "CHAIN_BACK",
        "VELCAP",
        "RESPAWN",
        "BOTTOM",
        "TRIGGER_MARKER",
        "BEHAVIOR",
        "SUCK",
        "UP",
        "ANY",
        "XDIR",
        "MOVEDURINGWIND",
        "IDLE",
        "shot",
        "COLLISION_Y",
        "MOVE",
        "SHOTOFFSET",
        "FROG",
        "SHOTTIME",
        "NOLIMIT",
        "RANGETILEWIDTH",
        "INTERVAL",
        "SHAKE_TIME",
        "ACCEL_Y",
        "TIMEON",
        "ONTIME",
        "TIMEOFF",
        "TIMEOFFSET",
        "VALVE",
        "S",
        "SCALE_COLLISION",
        "BLOCK_COLLIDE",
        "swingDir",
        "birder",
        "SONG",
        "MEAL",
        "MERIT",
        "ROSE",
        "MONEYDROP",
        "BIGMONEY",
        "CARDDROP",
        "LOOTDROP",
        "PL_LOOTSWAP",
        "dialog",
        "FAKE",
        "speed",
        "direction",
        "CENTER_L",
        "CENTER_R",
        "BOAT",
        "WATER",
        "TILE_SNAP",
        "SHAKE_LAYER",
        "SUDDEN_DEATH",
        "GOO_FREEZE",
        "MOVE_NO_WAIT",
        "stereoDepth",
        "AIRSHIP",
        "SPK_LOOTDROP",
        "FIRE",
        "FIRE_MIN",
        "FACING",
        "FIRE_MAX",
        "RANGE_Y",
        "EDGE",
        "PATROL_Y",
        "PATROL_OFFSET_X",
        "PATROL_OFFSET_Y",
        "PATROL_NEGX",
        "PATROL_NEGY",
        "TIME_OFFSET_X",
        "VEL",
        "FIRE_PREDICT",
        "SWOOP_RANGE",
        "FIRE_TIME",
        "FIRE_TIME_OFFSET",
        "FIRE_CYCLE_FIX",
        "FIRE_HORZ",
        "FIRE_VEL",
        "FIRE_PAUSE",
        "FIRE_CULL_SCREEN",
        "FIRE_INRANGE",
        "FIRE_INRANGE_Y",
        "SCREEN_BOUND",
        "VALVEXT",
        "VALVEXT2",
        "VALVEXT3",
        "VALVEONTIME",
        "TILES",
        "TIMEGROW",
        "TIMESHRINK",
        "ONE",
        "EXTENDED",
        "TILESEXT",
        "DISP",
        "OFFSET",
        "OIL_LAVA_DEATH",
        "TIME_ON",
        "TIME_OFF",
        "TIME_WARNING",
        "ID",
        "LOC",
        "MAX",
        "SPAWN_MIN",
        "SPAWN_MAX",
        "SPAWN_COOLDOWN",
        "TIME_MIN",
        "TIME_MAX",
        "SPAWN_ALLDEAD",
        "SPAWN_SAMEALLOWED",
        "PLAYER_COUNT",
        "CLOSE_TIME_MIN",
        "CLOSE_TIME_MAX",
        "CLOSE_GEM_TIME",
        "CLOSE_GEM_COUNT",
        "TWO_PLAYER_ADD_TIME",
        "ONSCREEN_OFFSET_X",
        "BATTLE_MODE",
        "CONTROLLER",
        "PLAYER_ZONE",
        "ALT_TIME_MIN",
        "ALT_TIME_MAX",
        "CAP",
        "SPAWNFROM",
        "TIME_SPEED",
        "WAITTIME",
        "NODEWAITTIME",
        "TIMEOFFSETPERC",
        "EASE_TYPE",
        "WAITTIMEADD",
        "VALVESTOP",
        "VALVEREVERSE",
        "SHAKESTART",
        "SHAKEEND",
        "DECELTIME",
        "ACCELTIME",
        "BACK",
        "NO_PLAGUE",
        "SMOKE",
        "CHUD",
        "GROUP",
        "PLK_FISH",
        "FISH",
        "out",
        "ANIM",
        "SEQUENCE",
        "rooster",
        "STENCIL",
        "TIME_X",
        "TIME_Y",
        "COLLISION_LAYER",
        "offset",
        "PARTNER",
        "rotation",
        "DIR",
        "WIND_VELCAP",
        "WIND_POWER",
        "WIND_DISTANCE",
        "appearOn",
        "enter",
        "enterOnce",
        "lowhealth",
        "player",
        "dialogue",
        "creditsWindowBreak",
        "credits",
        "NO_GHOST",
        "ICE",
        "CHEAT_PLAT",
        "SWING_HEIGHT",
        "BASH",
        "GOO",
        "CHAIN_SEPARATION",
        "card",
        "noSpike",
        "PATROL_NOEASE",
        "PATROL_TIME_OFFSET",
        "CHASE_SPEED",
        "CHASE_WAIT",
        "CHASE_ONLYWAIT",
        "THROW_TIME",
        "THROW_X",
        "THROW_Y",
        "THROW_TIME_OFFSET",
        "THROW_TOP",
        "THROW_BOTTOM",
        "THROW_PAUSE",
        "JUMP_DISTANCE",
        "REDUCEY",
        "DISPLAY",
        "ELEVATOR_BLOCK",
        "WHITELAYER",
        "BLACKLAYER",
        "DISABLE",
        "BLACKRIGHT",
        "BLACKLEFT",
        "NOSTARTSTRIKE",
        "ALWAYSDARK",
        "INIT_FORM",
        "ABORT",
        "JUMP_HEIGHT",
        "STD",
        "CONVEYOR",
        "WAIT_FOR_PLAYER",
        "COLLISION",
        "KING_EXP",
        "HACK_OFFSET",
        "SPLINE_RESET",
        "dialogEvent",
        "dialogPost",
        "dialogDefeat",
        "dialogRun",
        "railLeft",
        "railRight",
        "railOffscreen",
        "triggerSit",
        "dialogSit",
        "layerCheck",
        "noReward",
        "dialogInitial",
        "d",
        "shop_nofunds",
        "shop",
        "shoptrigger",
        "cardGame",
        "shopClose",
        "dialogOrder",
        "postAnim",
        "talkAnim",
        "postPurchaseAnim",
        "prePurchaseAnim0",
        "anim1",
        "anim2",
        "payOffShortDialog",
        "npcName",
        "paletteAlt",
        "underHUD",
        "zPos",
        "zPosBack",
        "zPosBackCard",
        "visible",
        "physics",
        "keepout",
        "behaviorHit",
        "timeoutAnim",
        "RECT",
        "ROW",
        "COLLISION_LEFT",
        "SPECTER",
        "KING",
        "NOFUZZY",
        "FUZZY_BIGGER",
        "COLLISION_RIGHT",
        "DEPTH_OFFSET",
        "SPECTER_STAGE",
        "AVOID_PLAYER",
        "BLAST_AWAY",
        "FORCE_PAL",
        "DISABLE_L",
        "DISABLE_R",
        "STARTOFF",
        "animSequenceTrigger",
        "USE_Y",
        "triggerSFX",
        "LIFE",
        "DISTANCEDOWN",
        "BALLOON",
        "WINCH",
        "NOJINGLE",
        "NOCOMPLETE",
        "SECRET",
        "OFFSCREEN",
        "dialogNoBuy",
        "dialogBuy",
        "dialogOff",
        "COLOR_R",
        "COLOR_G",
        "COLOR_B",
        "SPAWNIFNONE",
        "dir",
        "BORDER",
        "CANWRAP",
        "ACTUAL",
        "noSpawn",
        "noSpawnDestroy",
        "NOATTACK",
        "NOCLIMB",
        "LAYER2",
        "LAYER3",
        "NOPHYSICS",
        "NOPLAYER",
        "DIRT",
        "BARREL",
        "CANNON",
        "PBOMB",
        "feat",
        "NOENGAGE",
        "COUNT",
        "RED",
        "TURN_TIME",
        "PATROL_OFFSET",
        "HEIGHT_SPEED",
        "DISTANCE_OFFSET",
        "PATROL_WIDTH",
        "TURN_PLAYER",
        "TURN_PLAYER_SPEED",
        "HEIGHT_CYCLE",
        "NO_JUMP",
        "STATUE",
        "JUMPBACK_Y",
        "JUMPTHROW",
        "JUMP_CYCLE",
        "JUMP_CYCLE_OFFSET",
        "CHECK_EDGE_WIDTH",
        "WRAP",
        "GRAVITY",
        "killIfCinema",
        "STREET",
        "LENGTH",
        "QUICK",
        "MAX_SPEED",
        "TRANSLATION_OFFSET_Y",
        "TRANSLATION_OFFSET_Z",
        "SHOT_COUNT",
        "SHOT_VEL_Y",
        "SHOT_DROP_TIME",
        "TARGET",
        "FLIP",
        "NOPLAYERBOUNCE",
        "ANIM_OFFSET_X",
        "ANIM_OFFSET_Y",
        "animResource2",
        "ART_LAYER",
        "NO_TARGET",
        "DEACTIVATE_TIME",
        "TIME_CYCLE_OFFSET",
        "VEL_ENTER",
        "VEL_EXIT",
        "SHOOT",
        "SHOOT_FLIP",
        "TIME_ENTER",
        "TIME_EXIT",
        "TIME_IDLE",
        "CANT_EXIT",
        "SIN_DISTANCE_X",
        "SIN_SPEED_X",
        "SIN_DISTANCE_Y",
        "SIN_SPEED_Y",
        "VEL_OVERRIDE_X",
        "MAXVEL",
        "HITTABLE",
        "SPEED_FALL",
        "SPEED_RESET",
        "OFFOPT",
        "MAX_TILE",
        "TIME_RESET",
        "LIFT",
        "PAIR",
        "CANT_BASH_PAST_IDLE",
        "NO_CRUSH",
        "DISTANCE_X",
        "SEARCH_X",
        "SEARCH_SPEED",
        "SEARCH_OFFSET_X",
        "RESPAWN_WAIT_MIN",
        "RESPAWN_WAIT_MAX",
        "JUMP_WAIT_MIN",
        "JUMP_WAIT_MAX",
        "WAIT_MIN",
        "WAIT_MAX",
        "DECREASE",
        "PERSISTENTCULL",
        "SHAKEIFON",
        "nolid",
        "SPIKE",
        "SIZE_X",
        "SIZE_Y",
        "ON",
        "VERT",
        "NOBOUNCE",
        "FADE",
        "MARKER",
        "TIME_TYPE",
        "CAST_DIR",
        "ROOM",
        "DARK",
        "FRAME",
        "START_OFFSET",
        "END_OFFSET",
        "HOLD",
        "RETURN_VEL",
        "TAIL",
        "RETRACT_TIME",
        "SPIN",
        # Bool
        "SLEEP",
        "RUN",
        "LEFT",
        "RIGHT",
        "FACING",
        "stationary",
        "onExitRange",
        "UNBREAKABLE",
        "GRAVE",
        "noTreasure",
        "PHASE_IN",
        "GOO",
        "PATROL",
        "wanderAlwaysMove",
        "wanderAlwaysMoveNT",
        "ESCAPE",
        "unlockAttack",
        "END",
        "ghost",
        "QUICK_CAST",
        "GAMEPLUS",
        "QUICKCAST",
        # Integer
        "index",
        "Value",
        "INDEX_GROUP",
        "bossType",
        "DIR",
        "MONEYDROP",
        "tileRange",
        "ORDER",
        "VALUE",
        "SONG",
        "TREASUREID",
        "price",
        "INDEX",
        "WATER_STOP",
        "MAX",
        "RAND",
        "TYPE",
        "MERIT",
        "credits",
        "windowBreakIndex",
        "fancyPayOffIndex",
        "offset",
        "ID",
        "ART_ID",
        "IDLE_REPS",
        # Float
        "spawnExtentX",
        "spawnExtentY",
        "OFFSET_X",
        "OFFSET_Y",
        "EXPLOSION_TIME",
        "WAKE_TIME",
        "WAKE_RANGE_X",
        "PATROL_X",
        "PATROL_OFFSET_X",
        "STOPTIME",
        "STARTTIME",
        "WALK_SPEED",
        "RUN_SPEED",
        "DIST_SIDE",
        "DIST_ABOVE",
        "DIST_SIDE2",
        "DIST_ABOVE2",
        "TIME_WAIT_ONE",
        "TIME_WAIT_TWO",
        "MOVE_TIME",
        "MOVE_TIME2",
        "TIME_OFFSET",
        "riseY",
        "SPEED",
        "swingAngle",
        "swingSpeed",
        "length",
        "zpos",
        "DROP_X",
        "RANGE",
        "LAUNCH_X",
        "LAUNCH_Y",
        "SPAWN_TIME",
        "OFFSETX",
        "SPAWNTIME",
        "WAITTIME",
        "PERC",
        "SCREEN_PERC",
        "HEIGHT",
        "HANG",
        "HEALTH",
        "WAIT",
        "SPAWNOFFSET_Y",
        "DISTANCE_X",
        "SPEED_X",
        "SPEED_Y",
        "SPAWNOFFSET_X",
        "tileRange",
        "tileRangeY",
        "PRIORITY",
        "enterXRange",
        "TIMEON",
        "TIMEOFF",
        "TIMEOFFSET",
        "CHARGE_MAX_X",
        "CHARGE_MAX_Y",
        "idleTime",
        "bounce_vel",
        "engageX",
        "RANGE_X",
        "bounceHeight",
        "SHOTTIME",
        "DROP_ENGAGE_X",
        "RANGE_Y",
        "WAIT_TIME",
        "patrolRangeX",
        "wanderRangeX",
        "TIME",
        "START_WAIT",
        "interactX",
        "interactOffsetX",
        "interactY",
        "zPos",
        "wanderSpeed",
        "offset",
        "walkSpeed",
        "DELAY_TIME",
        "openHeight",
        "ropeWaitTime",
        "PUSH_SPEED",
        "distanceRange",
        "VALUE",
        "GROUND_TIME",
        "ROOM_TIME",
        "TRIGGER_RANGE_X",
        "TIME_ON",
        "VANISH_TIME",
        "SPEED_FALL",
        "SPEED_RESET",
        "MAX_TILE",
        "TIME_RESET",
        "BASH_MOVE",
        "ENGAGE_X",
        "ENGAGE_Y",
        "SPEED_FLY",
        "JUMP",
        "COOLDOWN",
        "CHARGE_TIME",
        "CASTING_TIME",
        "appearTime",
        # Unk
                    "TREASUREK",
        "RIDE",
        "RED",
        "SINGLE",
        "OFFSCREEN",
        "NO_SCREEN",
        "NO_COLLIDE",
        "BOMBER",
        "STONE",
        "ONE",
        "SCRIPTED",
        "palWorld",
        "envTime",
        "useTint",
        "round",
        "animSequenceJPN",
        "anchorLeft",
        "anchorRight",
        "credits",
        "PATH",
        "IN_ORDER",
        "REVERSE",
        "EDGE",
        "NO_ENGAGE",
        "SLEEP",
        "ALT",
        "STOPTIME",
        "STARTTIME",
        "ROOM",
        "CULL_ONSCREEN",
        "NO_GOO_CHANGE",
        "PIT_IMMUNITY",
        "USE_COLLISION",
        "LEVEL_TIME",
        "DIST_SIDE",
        "DIST_ABOVE",
        "DIST_SIDE2",
        "DIST_ABOVE2",
        "TIME_WAIT_ONE",
        "TIME_WAIT_TWO",
        "MOVE_TIME",
        "MOVE_TIME2",
        "TIME_OFFSET",
        "BIRDER",
        "DIR",
        "CLIMB",
        "COOP_ONLY",
        "CUSTOM",
        "L",
        "R",
        "U",
        "D",
        "SECRET",
        "secret",
        "FLOAT",
        "RISE",
        "BUBBLE",
        "STILL",
        "BOSS",
        "NUDGE_Y",
        "PERCY",
        "SCHOLAR",
        "NOTINWATER",
        "noHit",
        "noSpike",
        "TREASUREID",
        "dialog",
        "PL_CHEST_NORMAL",
        "WILL_BOOST",
        "DARKNESS_BOOST",
        "NOCLIMB",
        "SOFT",
        "WAIT_PLAYER_CONTROL",
        "MONEYDROP",
        "LAUNCH_X",
        "LAUNCH_Y",
        "WATERSPURT",
        "DIGTHROUGH",
        "DIGTHROUGHFLOOR",
        "MOLEWATER",
        "CARROT",
        "TONIC",
        "COOP_KILL",
        "ROOMTIME",
        "PERSISTENTCULL",
        "HORNJUMP",
        "CULL_DEFAULT",
        "QUICKSPAWN",
        "SPAWNSFX",
        "MAX",
        "STARTSPAWN",
        "START_AT_SPAWN",
        "NO_WARNING",
        "CONTROLLER",
        "PLAYER_ZONE",
        "RAND",
        "SPAWNBYCAMERA",
        "SPAWNBYROOM",
        "PERC_SIDE",
        "SCREEN_PERC",
        "SINGLE_ONLY",
        "HEIGHT",
        "HANG",
        "PLAGUE",
        "BEHIND_HUD",
        "IGNORELIGHTNING",
        "SPAWNOFFSET_Y",
        "DISTANCE_X",
        "SPEED_X",
        "SPEED_Y",
        "SCREENWRAP_Y",
        "AUTORESPAWN",
        "SPAWNOFFSET_X",
        "stationary",
        "DARK",
        "STEEL",
        "WATER",
        "CHEAT_PLAT",
        "BLOCK",
        "MOVE",
        "CHAIN",
        "BREAKABLE",
        "COLLECTINPF",
        "COLLECT_HIDE",
        "BEHIND_PF",
        "COLLECT_BEHIND",
        "BACK",
        "ELECTRIC",
        "INFINITE_HEALTH",
        "SMALL",
        "coopMultiHit",
        "CHARGE_MAX_Y",
        "fall_in",
        "warpY",
        "warpAware",
        "edge",
        "onebreak",
        "jumpChase",
        "jumpDown",
        "NO_X_MOVEMENT",
        "NOPHYSICS",
        "LEGACY_PUSHABLE",
        "CAMPFIRE",
        "SLEEPING",
        "WAIT_TIME",
        "PIT_FALL",
        "above",
        "bottom",
        "TIME",
        "WAIT",
        "START_WAIT",
        "timeoutRare",
        "palettePlayerArmor",
        "timeoutOnIdle",
        "OLDVILLAGE",
        "CULLROOM",
        "UPDATESPAWN",
        "ROOM_LOCK",
        "SPEED",
        "JUMP",
        "OPPOSITE",
        "TOP",
        "FORCE_ENTER",
        "dialogOff",
        "FIRE",
        "RESPAWN",
        "SPIT",
        "LOOTDROP",
        "MERIT",
        "START_ON",
        "DONE",
        "OBEY_Y",
        "OBEY_NEG_Y",
        "SPAWNIFNONE",
        "SPAWNBOSS",
        "APPLE",
        "LONG",
        "WARP",
        "clouds",
        "rain",
        "clearrain",
        "SO_XB",
        "LAYER2",
        "LAYER3",
        "SEPIA",
        "underHUD",
        "runAround",
        "animSequence",
        "WITCH",
        "JUMP_IN",
        "STAY_DOWN",
        "POS_X",
        "POS_Y",
        "HACK_AUTOHIGH",
        "NOBLINKSLASH",
        "old",
        "tower",
        "shieldK",
        "FACING",
        "START_IDLE",
        "FOLLOW_FIRE_MARKERS",
        "floorCheck",
        "water",
        "CHALLENGE",
        "SPIKE_COLLIDE",
        "GAMEPLUS",
        "noEdge",
        "patrol",
        "NO_PIT",
        "VP",
        "TIME_ON",
        "noclimb",
        "HORN",
        "SPARKLEIN",
        "SPARKLE_WARNING",
        "NOGRAV",
        "HUD_HIDE",
        "UP",
        "COLLIDE_SLIDE",
        "ALWAYS_FACE_PLAYER",
        "TRIGGER_BOTH_SIDES",
        "IDLE",
        "BUG_FIGHT",
        "RANGE",
        "COOLDOWN",
        "NO_WALL_SWITCH",
        "CRAWL_PLAYER",
        "TYPE",
        "FORWARD",
        "TALL",
        "startOut",
        "tombShow",
    ]
    for i in range(len(parameterList)):
        stri = parameterList[i]
        hash = YCG_Hash(stri, len(stri), 123456789)
        parameterMap[hash] = stri

    # print("Unique Property Value Sets:")
    # print("---------------------------")
    # discovered = 0
    # discoveredMax = 0
    # for i in range(len(lvb.propertyValueSetList)):
    #     propertyValue = lvb.propertyValueSetList[i]
    #     if propertyValue.hash in parameterMap.keys():
    #         print("Property %d Hash: %s   Value: %s" % (i, parameterMap[propertyValue.hash], lvb.valueStringListMap[propertyValue.stringOffset]))
    #         discovered += 1
    #     else:
    #         print("Property %d Hash: 0x%08X   Value: %s" % (i, propertyValue.hash, lvb.valueStringListMap[propertyValue.stringOffset]))
    #     discoveredMax += 1
    # print("Discovered %d / %d" % (discovered, discoveredMax))
    # print("")

    map_name = "Plains"

    layer_id = 1
    object_id = 1

    xml_map = Element("map")
    xml_map.set("version", "1.2")
    xml_map.set("tiledversion", "1.3.3")
    xml_map.set("orientation", "orthogonal")
    xml_map.set("renderorder", "right-down")
    xml_map.set("width", "25")
    xml_map.set("height", "25")
    xml_map.set("tilewidth", "16")
    xml_map.set("tileheight", "16")
    xml_map.set("infinite", "0")
    # xml_map.set("nextlayerid", "3")
    # xml_map.set("nextobjectid", "2")

    comment = Comment("Generated using ShovelKnightRE: https://github.com/aknetk/ShovelKnightRE")
    xml_map.append(comment)

    xml_tileset = SubElement(xml_map, "tileset")
    xml_tileset.set("firstgid", "1")
    xml_tileset.set("source", "Plains.tsx")
    xml_tileset = SubElement(xml_map, "tileset")
    xml_tileset.set("firstgid", "785")
    xml_tileset.set("source", "PlainsWaterfall.tsx")

    tilebuffer = [[0] * 64 for i in range(64)]

    columncount = 28
    for i in range(len(ltb.staticVertexDataList) >> 2):
        # Z formation
        v1 = ltb.staticVertexDataList[i * 4 + 0]
        v2 = ltb.staticVertexDataList[i * 4 + 1]
        v3 = ltb.staticVertexDataList[i * 4 + 2]
        v4 = ltb.staticVertexDataList[i * 4 + 3]

        # Compare UVs to determine orientation
        flip_x = v1[3] > v2[3]
        flip_y = v1[4] > v2[4]

        mean_x = (v1[0] + v2[0] + v3[0] + v4[0]) / 4
        mean_y = (v1[1] + v2[1] + v3[1] + v4[1]) / 4

        x = mean_x / 0.1 + 240.0 # / 0.1, as this is undoes what game does internally
        y = mean_y / 0.1 + 160.0 # / 0.1, as this is undoes what game does internally
        z = v1[2]
        u = v1[3] * 512.0
        v = v1[4] * 512.0

        tile_x = math.floor(x / 16.0)
        tile_y = math.floor(y / 16.0)
        cell_x = math.floor(u / 18.0)
        cell_y = math.floor(v / 18.0)
        tilebuffer[tile_x][tile_y] = math.floor(cell_x + cell_y * columncount) + 1

    normal_tile_count = 401
    first_sheet_tile_count = 784

    layerList_string = ""
    for i in range(len(ltb.layerInfoList)):
        layer = ltb.layerInfoList[i]
        visible = 1
        if layer.endX - layer.startX < -1:
            continue
        if layer.endY - layer.startY < -1:
            continue

        xml_layer = SubElement(xml_map, "layer")
        xml_layer.set("id", str(layer_id))
        xml_layer.set("name", layer.name.decode("utf8").split('\0', 1)[0])
        xml_layer.set("width", str(layer.endX - layer.startX + 1))
        xml_layer.set("height", str(layer.endY - layer.startY + 1))
        xml_layer.set("offsetx", str(layer.startX * 16))
        xml_layer.set("offsety", str(layer.startY * 16))
        xml_layer.set("visible", str(visible))
        layer_id += 1

        xml_data = SubElement(xml_layer, "data")
        xml_data.set("encoding", "csv")

        xml_properties = SubElement(xml_layer, "properties")
        xml_property = SubElement(xml_properties, "property")
        xml_property.set("name", "SCROLL_X_MULT")
        xml_property.set("type", "float")
        xml_property.set("value", "%f" % layer.cameraMultX)
        xml_property = SubElement(xml_properties, "property")
        xml_property.set("name", "SCROLL_Y_MULT")
        xml_property.set("type", "float")
        xml_property.set("value", "%f" % layer.cameraMultY)

        if layer.isUsingStaticVertexBuffer != 0:
            csv = ""
            first = True
            for ty in range(layer.endY - layer.startY + 1):
                for tx in range(layer.endX - layer.startX + 1):
                    if first:
                        csv += "%d" % (int(tilebuffer[tx][layer.endY - ty]))
                        first = False
                    else:
                        csv += ",%d" % (int(tilebuffer[tx][layer.endY - ty]))
            xml_layer.set("offsetx", "0.0")
            xml_layer.set("offsety", "0.0")
            xml_data.text = csv
        else:
            chunk_text = ""
            chunkStart = layer.chunkIDStart
            for cy in range(layer.chunkYCount):
                for cx in range(layer.chunkXCount):
                    chunkID = chunkStart + cx + cy * layer.chunkXCount
                    tileStart = ltb.chunkInfoList[chunkID].tileBufferStart
                    if tileStart > 0:
                        csv = ""
                        first = True
                        for ty in range(16):
                            for tx in range(16):
                                tiledata = ltb.tileBufferList[tileStart + tx + ty * 16]
                                isSolid = tiledata & 0x8000
                                flip_x = tiledata & 0x2000
                                flip_y = tiledata & 0x4000
                                tile_id = tiledata & 0xFFF
                                tiled_out = tile_id

                                if "BGWATERFALL" in layer.name.decode():
                                    tiled_out += first_sheet_tile_count

                                if tiled_out != 0:
                                    if flip_x != 0:
                                        tiled_out |= 0x80000000
                                    if flip_y != 0:
                                        tiled_out |= 0x40000000
                                if first:
                                    csv += "%d" % (int(tiled_out))
                                    first = False
                                else:
                                    csv += ",%d" % (int(tiled_out))

                        xml_chunk = SubElement(xml_data, "chunk")
                        xml_chunk.set("x", str(cx * 16))
                        xml_chunk.set("y", str(cy * 16))
                        xml_chunk.set("width", "16")
                        xml_chunk.set("height", "16")
                        xml_chunk.text = csv

    for b in range(len(lvb.rectangleBatchList)):
        batch = lvb.rectangleBatchList[b]
        xml_objectgroup = SubElement(xml_map, "objectgroup")
        xml_objectgroup.set("id", str(layer_id))
        xml_objectgroup.set("visible", "false")
        if batch.hash in parameterMap.keys():
            print(parameterMap[batch.hash])
            xml_objectgroup.set("name", parameterMap[batch.hash])
        else:
            xml_objectgroup.set("name", "Rect Layer %08X" % batch.hash)
        layer_id += 1
        for r in range(batch.start, batch.start + batch.count):
            recta = lvb.rectangleInfoList[r]
            xml_object = SubElement(xml_objectgroup, "object")
            xml_object.set("x", str(recta.x))
            xml_object.set("y", str(recta.y))
            xml_object.set("width", str(recta.width))
            xml_object.set("height", str(recta.height))
            xml_object.set("id", str(recta.id))
            object_id = recta.id + 1

    # parameterMap
    xml_objectgroup = SubElement(xml_map, "objectgroup")
    xml_objectgroup.set("id", str(layer_id))
    xml_objectgroup.set("name", "Object Layer %08X" % 0xDEADBEEF)
    layer_id += 1

    unk7s = {}
    # self.objectInfo = namedtuple("ObjectInfo", "unkHash layerNameHash x y scalex scaley unk6 objectID unk7 gID propertyCount propertyIndexStart unk11")

    for i in range(len(lvb.objectInfoList)):
        object = lvb.objectInfoList[i]
        oID = object.objectID & 0xFFF

        xml_object = SubElement(xml_objectgroup, "object")
        xml_object.set("x", str(object.x))
        xml_object.set("y", str(object.y))
        if oID in objectNameDict.keys():
            xml_object.set("name", objectNameDict[oID])
        else:
            xml_object.set("name", "UnknownObject %d" % oID)
        xml_object.set("id", str(object.gID & 0xFFFF))
        xml_point = SubElement(xml_object, "point")
        object_id += 1

        unk7s[object.unk7] = object.unk7

        xml_properties = SubElement(xml_object, "properties")

        p_count = lvb.objectPropertyCountMap[oID]
        p_start = object.propertyIndexStart
        p_end = p_start + object.propertyCount
        for p in range(p_start, p_end):
            valueSet = lvb.propertyValueSetList[p]
            property_name = "0x%08X" % valueSet.hash
            property_value = ""
            if valueSet.hash in parameterMap.keys():
                property_name = parameterMap[valueSet.hash]
            if valueSet.stringOffset in lvb.valueStringListMap.keys():
                property_value = lvb.valueStringListMap[valueSet.stringOffset]

            xml_property = SubElement(xml_properties, "property")
            xml_property.set("name", property_name)
            xml_property.set("type", "string")
            xml_property.set("value", property_value)

    print("unk7s")
    for u in unk7s.keys():
        print("u: %d" % u)

    open("../Scenes/" + map_name + ".tmx", "w").write(prettifyXML(xml_map))

    paletteInfo = ltb.textureFormatInfoList[0]
    ltb.file.seek(ltb.ltb_start + ltb.attachedFileList[0])
    paletteBytes = ltb.file.read(paletteInfo.size)

    print("width %d height %d size %d" % (paletteInfo.width, paletteInfo.height, paletteInfo.size))

    wflz = WFLZ()
    for i in range(len(ltb.attachedFileList)):
        ltb.file.seek(ltb.ltb_start + ltb.attachedFileList[i])

        info = ltb.textureFormatInfoList[i]
        if info.isCompressed != 0:
            bytearr = wflz.decomp_file(ltb.file)

            if info.width * info.height * 4 == len(bytearr):
                image = Image.frombytes('RGBA', (info.width, info.height), bytes(bytearr), 'raw')
                image.save("file_name_%d.png" % i)
            else:
                bytearrRGBA = [0] * len(bytearr) * 4
                for c in range(len(bytearr)):
                    cp = int(bytearr[c] * 32 / 255) << 2
                    bytearrRGBA[c * 4 + 0] = paletteBytes[cp + 0]
                    bytearrRGBA[c * 4 + 1] = paletteBytes[cp + 1]
                    bytearrRGBA[c * 4 + 2] = paletteBytes[cp + 2]
                    bytearrRGBA[c * 4 + 3] = paletteBytes[cp + 3]
                image = Image.frombytes('RGBA', (info.width, info.height), bytes(bytearrRGBA), 'raw')
                image.save("file_name_%d.png" % i)
        else:
            bytearr = ltb.file.read(info.size)
            if info.width * info.height * 4 == len(bytearr):
                image = Image.frombytes('RGBA', (info.width, info.height), bytes(bytearr), 'raw')
                image.save("file_name_%d.png" % i)
    print("")

if __name__ == '__main__':
    # Verify the file exist and an arg was giving
    if not len(sys.argv) >= 2:
        _exit("Error: Please specify a target .ltb file.")
    if not Path(sys.argv[1]).is_file() and not Path(sys.argv[1]).is_dir():
        _exit("Error: The file '%s' was not found." % (sys.argv[1]))
    if not len(sys.argv) >= 3:
        _exit("Error: Please specify a target .lvb file.")
    if not Path(sys.argv[2]).is_file() and not Path(sys.argv[2]).is_dir():
        _exit("Error: The file '%s' was not found." % (sys.argv[2]))

    # Run it
    # os.chdir(Path(sys.argv[1]).parent)
    ltb = LTBClass(Path(sys.argv[1]))
    lvb = LVBClass(Path(sys.argv[2]))
    LTBandLVBtoTiled(ltb, lvb)
    # LTBandLVBtoRSDKScene(ltb, lvb, "Plains")

_exit("Log: Program finished.")
