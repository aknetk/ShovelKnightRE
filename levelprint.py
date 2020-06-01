#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
    def comp_file(self, file):
        return bytearray(0)

def ReadType(file, type):
    return struct.unpack(type, file.read({ "B": 1, "H": 2, "I": 4 }[type]))[0]
def ReadTypeBE(file, type):
    return struct.unpack(">" + type, file.read({ "B": 1, "H": 2, "I": 4 }[type]))[0]
def ReadRSDKString(file):
    return file.read(ReadType(file, "B")).decode("utf-8").split('\0', 1)[0]
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
        unk_Count_0x00 = header[1]
        unk_Offset_0x00 = header[2]
        unk_Value_0x10 = header[3]
        unk_Count_0x10 = header[4]
        unk_Offset_0x10 = header[5]
        unk_Value_0x20 = header[6]
        unk_Count_0x20 = header[7]
        unk_Offset_0x20 = header[8]
        unk_Value_0x30 = header[9]
        unk_Count_0x30 = header[10]
        unk_Offset_0x30 = header[11]
        unk_Value_0x40 = header[12]
        unk_Count_0x40 = header[13]
        unk_Offset_0x40 = header[14]
        unk_Value_0x50 = header[15]
        unk_Count_0x50 = header[16]
        unk_Offset_0x50 = header[17]
        unk_Value_0x60 = header[18]
        unk_Count_0x60 = header[19]
        unk_Offset_0x60 = header[20]

        print("LayerObject Header:")
        print("-------------------")
        print("unk_Value_0x00: %d" % unk_Value_0x00)
        print("unk_Count_0x00: %d" % unk_Count_0x00)
        print("unk_Offset_0x00: 0x%X" % unk_Offset_0x00)
        print("")
        print("unk_Value_0x10: %d" % unk_Value_0x10)
        print("unk_Count_0x10: %d" % unk_Count_0x10)
        print("unk_Offset_0x10: 0x%X" % unk_Offset_0x10)
        print("")
        print("unk_Value_0x20: %d" % unk_Value_0x20)
        print("unk_Count_0x20: %d" % unk_Count_0x20) # 0x1C
        print("unk_Offset_0x20: 0x%X" % unk_Offset_0x20)
        print("")
        print("unk_Value_0x30: %d" % unk_Value_0x30)
        print("unk_Count_0x30: %d" % unk_Count_0x30) # 0x18
        print("unk_Offset_0x30: 0x%X" % unk_Offset_0x30)
        print("")
        print("unk_Value_0x40: %d" % unk_Value_0x40)
        print("unk_Count_0x40: %d" % unk_Count_0x40) # 0x8
        print("unk_Offset_0x40: 0x%X" % unk_Offset_0x40)
        print("")
        print("unk_Value_0x50: %d" % unk_Value_0x50)
        print("unk_Count_0x50: %d" % unk_Count_0x50) # 0x90, the realCount = count - 1
        print("unk_Offset_0x50: 0x%X" % unk_Offset_0x50)
        print("")
        print("unk_Value_0x60: %d" % unk_Value_0x60)
        print("unk_Count_0x60: %d" % unk_Count_0x60) # Strings
        print("unk_Offset_0x60: 0x%X" % unk_Offset_0x60)
        print("")

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
            106: "SwordSkeleton",
            112: "GemPileWall",
            132: "Skull",
            137: "GemSmall",
            147: "GreenDragon",
            150: "BossBlackKnightPlains",
            154: "Bubble",
            161: "BubbleDragon",
            162: "BreakableWall",
        }


        file.seek(lvb_start + unk_Offset_0x00)
        for i in range(unk_Count_0x00):
            packed = struct.unpack("II", file.read(0x8))
            # if packed[0] in objectNameDict.keys():
            #     print("%d %d   %s" % (packed[0], packed[1], objectNameDict[packed[0]]))
            # else:
            print("%d %d" % (packed[0], packed[1]))
        print("")

        self.objectInfo = namedtuple("ObjectInfo", "unk0 hash x y unk4 unk5 unk6 objectID unk8 unk9 unk10 unk11")
        self.objectInfoList = [ None ] * unk_Value_0x10

        print("unk_Count_0x10:")
        file.seek(lvb_start + unk_Offset_0x10)
        for i in range(len(self.objectInfoList)):
            self.objectInfoList[i] = self.objectInfo._make(struct.unpack("IIffffIIIIII", file.read(0x30)))
            object = self.objectInfoList[i]
            print("unk0 0x%X hash 0x%X x %f y %f unk4 %f unk5 %f unk6 0x%X objectID 0x%X unk8 0x%X unk9 0x%X unk10 0x%X unk11 0x%X" % (object.unk0, object.hash, object.x, object.y, object.unk4, object.unk5, object.unk6, object.objectID, object.unk8, object.unk9, object.unk10, object.unk11))
        print("")

        print("unk_Count_0x20:")
        print("-------------------")
        file.seek(lvb_start + unk_Offset_0x20)
        for i in range(unk_Count_0x20):
            object = struct.unpack("IIIII", file.read(0x14))
            print("0x%08X 0x%02X %02d %02d %d" % (object[0], object[1], object[2], object[3], object[4]))
        print("")

        print("unk_Count_0x30:")
        print("-------------------")
        file.seek(lvb_start + unk_Offset_0x30)
        for i in range(unk_Count_0x30):
            object = struct.unpack("IIIIIi", file.read(0x18))
            print("0x%08X 0x%04X 0x%03X 0x%03X %d %d" % (object[0], object[1], object[2], object[3], object[4], object[5]))
        print("")

        print("unk_Count_0x40:")
        print("-------------------")
        file.seek(lvb_start + unk_Offset_0x40)
        for i in range(unk_Count_0x40):
            object = struct.unpack("II", file.read(0x8))
            print("0x%08X 0x%08X" % (object[0], object[1]))
        print("")

        print("unk_Count_0x50:")
        print("-------------------")
        file.seek(lvb_start + unk_Offset_0x50)
        for i in range(unk_Count_0x50 - 1):
            object = struct.unpack("IIIIIIIIIIIII32sIfIIIIIIIIIIIII", file.read(0x90))
            print("%f %f %f %f" % (object[0], object[1], object[2], object[3]))
            print("0x%08X 0x%08X 0x%08X 0x%08X" % (object[4], object[5], object[6], object[7]))
            print("0x%08X 0x%08X 0x%08X 0x%08X" % (object[8], object[9], object[10], object[11]))
            print("0x%08X %s 0x%08X %f" % (object[12], object[13].decode("utf8").split("\0", 1)[0], object[14], object[15]))
            print("")
        print("")

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
        layerName = layer.name.decode("utf-8").split('\0', 1)[0]
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
        layerName = layer.name.decode("utf-8").split('\0', 1)[0]
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
        106: "SwordSkeleton",
        112: "GemPileWall",
        132: "Skull",
        137: "GemSmall",
        147: "GreenDragon",
        150: "BossBlackKnightPlains",
        154: "Bubble",
        161: "BubbleDragon",
        162: "BreakableWall",
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

    # Print Layers
    for i in range(len(ltb.layerInfoList)):
        layer = ltb.layerInfoList[i]
        print("Layer \"%s\"" % layer.name.decode())
        # print("   Tile Start X: %d" % layer.startX)
        # print("   Tile Start Y: %d" % layer.startY)
        # print("   Tile End X: %d" % layer.endX)
        # print("   Tile End Y: %d" % layer.endY)
        # print("   Camera Mult X: %f" % layer.cameraMultX)
        # print("   Camera Mult Y: %f" % layer.cameraMultY)
        # print("   Layer Offset X: %f" % layer.offsetX)
        # print("   Layer Offset Y: %f" % layer.offsetY)
        # print("   VertexBufferInfo Index: %d" % layer.vertexBufferInfoIndex)
        # print("   Is Using StaticVertexBuffer?: %d" % layer.isUsingStaticVertexBuffer)
        # print("   Chunk Column Count: %d" % (layer.chunkXCount))
        # print("   Chunk Row Count: %d" % (layer.chunkYCount))
        # print("   Chunk Start ID: %d" % (layer.chunkIDStart))
        print("   Unknowns: %f %f %f %f %f %f %d %d %d %d" % (layer.unk1, layer.unk2, layer.unk3, layer.unk4, layer.unk5, layer.unk6, layer.unkI7, layer.unkI8, layer.unkI9, layer.unkI10))
        print("")

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

    # Tilebuffer to Tiled CSV array
    map_format = "<?xml version=\"1.0\" encoding=\"UTF-8\"?> \n\
    <map version=\"1.2\" tiledversion=\"1.3.3\" orientation=\"orthogonal\" renderorder=\"right-down\" width=\"25\" height=\"14\" tilewidth=\"16\" tileheight=\"16\" infinite=\"0\" nextlayerid=\"3\" nextobjectid=\"2\"> \n\
        <tileset firstgid=\"1\" source=\"Plains.tsx\"/> \n\
        <tileset firstgid=\"785\" source=\"PlainsWaterfall.tsx\"/> \n\
%s \n\
        <objectgroup id=\"2\" name=\"Object Layer\"> \n\
%s \n\
        </objectgroup> \n\
    </map>"
    layer_format = "            <layer id=\"1\" name=\"%s\" width=\"%d\" height=\"%d\" offsetx=\"%f\" offsety=\"%f\" visible=\"%d\"> \n\
        <data encoding=\"csv\"> \n\
%s \n\
        </data> \n\
        <properties> \n\
            <property name=\"camScrollX\" type=\"float\" value=\"%f\" /> \n\
            <property name=\"camScrollY\" type=\"float\" value=\"%f\" /> \n\
        </properties> \n\
    </layer> \n"
    chunk_format = "                    <chunk x=\"%d\" y=\"%d\" width=\"%d\" height=\"%d\"> \n\
%s \n\
            </chunk> \n"
    object_format = "            <object x=\"%f\" y=\"%f\" name=\"%s\"> \n\
                <point/> \n\
            </object> \n"

    normal_tile_count = 401
    first_sheet_tile_count = 784

    layerList_string = ""
    for i in range(len(ltb.layerInfoList)):
        layer = ltb.layerInfoList[i]
        visible = 1
        if "_PLAGUE" in layer.name.decode():
            visible = 0
            continue
        if layer.endX - layer.startX < -1:
            continue
        if layer.endY - layer.startY < -1:
            continue

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
            layerList_string += layer_format % (layer.name.decode("utf-8").split('\0', 1)[0], layer.endX - layer.startX + 1, layer.endY - layer.startY + 1, 0, 0, visible, csv, layer.cameraMultX, layer.cameraMultY)
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
                        chunk_text += chunk_format % (cx * 16, cy * 16, 16, 16, csv)
            layerList_string += layer_format % (layer.name.decode("utf-8").split('\0', 1)[0], layer.endX - layer.startX + 1, layer.endY - layer.startY + 1, layer.startX * 16, layer.startY * 16, visible, chunk_text, layer.cameraMultX, layer.cameraMultY)

    objectNameDict = {
        1: "Player",
        3: "DirtBlockLarge",
        4: "DirtBlockSmall",
        11: "GemRed",
        12: "GemPink",
        13: "GemPile",
        14: "Platter",
        20: "Chest",
        25: "Unbreakable Checkpoint",
        29: "Back Forth Platform",
        37: "Beeto",
        57: "Slime",
        46: "FrontGrass",
        72: "Note",
        106: "SwordSkeleton",
        112: "GemPileWall",
        132: "Skull",
        137: "GemSmall",
        147: "GreenDragon",
        150: "BossBlackKnightPlains",
        154: "Bubble",
        161: "BubbleDragon",
        162: "BreakableWall",
    }

    objectList_string = ""
    for i in range(len(lvb.objectInfoList)):
        object = lvb.objectInfoList[i]
        oID = object.objectID & 0xFFF
        if oID in objectNameDict.keys():
            objectList_string += object_format % (object.x, object.y, objectNameDict[oID])
        else:
            objectList_string += object_format % (object.x, object.y, str(oID))

    open("../Scenes/Plains.tmx", "w").write(map_format % (layerList_string, objectList_string))

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
    # LTBandLVBtoTiled(ltb, lvb)
    # LTBandLVBtoRSDKScene(ltb, lvb, "Plains")

_exit("Log: Program finished.")
