import sys
import logging
import mmh3
import random

class HAMT(object):
    # http://www.valuedlessons.com/2009/01/popcount-in-python-with-benchmarks.html
    # http://graphics.stanford.edu/~seander/bithacks.html#CountBitsSetTable
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
    POPCOUNT_TABLE16 = [0] * 2**16
    for index in xrange(len(POPCOUNT_TABLE16)):
        POPCOUNT_TABLE16[index] = (index & 1) + POPCOUNT_TABLE16[index >> 1]

    @classmethod
    def popcount32_table16(cls, v):
        return (cls.POPCOUNT_TABLE16[ v        & 0xffff] +
                cls.POPCOUNT_TABLE16[(v >> 16) & 0xffff])

    @classmethod
    def popcount64_table16(cls, v):
        # logging.debug("popcount called with value %d" % v)
        return (cls.POPCOUNT_TABLE16[ v        & 0xffff] +
                cls.POPCOUNT_TABLE16[(v >> 16) & 0xffff] +
                cls.POPCOUNT_TABLE16[(v >> 32) & 0xffff] +
                cls.POPCOUNT_TABLE16[(v >> 48) & 0xffff])

    @staticmethod
    def hash64(v):
        ### Replacing this:
        return mmh3.hash64(v)[0]
        ### with this if you want to make a lot of collisions:
        ### return mmh3.hash64(v)[0] >> 56

    if sys.maxsize > 2 ** 32:
        popcount = popcount64_table16
        wordsize = 6
        hashfn = hash64
    else:
        popcount = popcount32_table16
        wordsize = 5
        hashfn = mmh3.hash
    hashmask = 2 ** wordsize - 1

    class NodeDict(object):
        def __init__(self):
            self.entries = {}

        def get(self, key, keyHash):
            try:
                return self.entries[key]
            except KeyError:
                raise

        def set(self, key, keyHash, val):
            self.entries[key] = val

        def __str__(self):
            return "%s" % self.entries

    class NodeTable(object):
        def __init__(self, level):
            # logging.debug("Creating new NodeTable with level %d" % level)
            self.level = level
            self.entryBitmap = 0
            self.typeBitmap = 0
            self.entries = []

        def get(self, key, keyHash):
            # logging.debug("--- Looking for %r with hash %d in level %d" % (key, keyHash, self.level))
            # logging.debug("entryBitmap is %s, typeBitmap is %s" % (bin(self.entryBitmap), bin(self.typeBitmap)))
            subhash = HAMT.hashmask & (keyHash >> (self.level * HAMT.wordsize))
            bitIndex = 1 << subhash
            # logging.debug("Subhash is %d, bitIndex is %s" % (subhash, bin(bitIndex)))
            if self.entryBitmap & bitIndex: # we have an entry
                entryIndex = HAMT.popcount(self.entryBitmap & (bitIndex - 1))
                # logging.debug("We have an entry, entryIndex is %d" % entryIndex)
                if self.typeBitmap & bitIndex: # it's a subtable
                    # logging.debug("The entry is a subtable, delegating")
                    return self.entries[entryIndex].get(key, keyHash)
                else:
                    # logging.debug("The entry is not a subtable, checking key equality")
                    if key == self.entries[entryIndex][0]:
                        # logging.debug("---------- end get %r %d %d" % (key, keyHash, self.level))
                        return self.entries[entryIndex][1]
                    else:
                        # logging.debug("Existing key %r doesn't match desired %r, raise KeyError" % (self.entries[entryIndex][0], key))
                        # logging.debug("---------- end get %r %d %d" % (key, keyHash, self.level))
                        raise KeyError(key)
            else:
                # logging.debug("---------- end get %r %d %d" % (key, keyHash, self.level))
                raise KeyError(key)

        def set(self, key, keyHash, val):
            # logging.debug("--- Setting value for %r with hash %d to %r in level %d" % (key, keyHash, val, self.level))
            # logging.debug("entryBitmap is %s, typeBitmap is %s" % (bin(self.entryBitmap), bin(self.typeBitmap)))
            subhash = HAMT.hashmask & (keyHash >> (self.level * HAMT.wordsize))
            bitIndex = 1 << subhash
            entryIndex = HAMT.popcount(self.entryBitmap & (bitIndex - 1))
            # logging.debug("Subhash is %d, bitIndex is %s, entryIndex is %d" % (subhash, bin(bitIndex), entryIndex))
            if self.entryBitmap & bitIndex: # we have an entry
                if self.typeBitmap & bitIndex: #it's a subtable
                    # logging.debug("We have an entry and it's a subtable, delegating")
                    self.entries[entryIndex].set(key, keyHash, val)
                    # logging.debug("---------- end set %r %d %r %d" % (key, keyHash, val, self.level))
                else: # not a subtable
                    # logging.debug("We have an entry but it's not a subtable, existing key is %r" % self.entries[entryIndex][0])
                    if key == self.entries[entryIndex][0]: # existing key, new value
                        # logging.debug("That's the same! replacing the tuple")
                        self.entries[entryIndex] = (key, val)
                        # logging.debug("---------- end set %r %d %r %d" % (key, keyHash, val, self.level))
                    else: # subhash collision! make a new NodeTable
                        # logging.debug("That's different! replacing the tuple with a new NodeTable with level %d" % (self.level + 1))
                        if (self.level + 1) * HAMT.wordsize > 2 ** HAMT.wordsize: # out of bits
                            logging.debug("Already at level %d, out of hash bits! Making a dict instead" % self.level)
                            newTable = HAMT.NodeDict()
                        else:
                            newTable = HAMT.NodeTable(self.level + 1)
                        newTable.set(self.entries[entryIndex][0], HAMT.hashfn(self.entries[entryIndex][0]), self.entries[entryIndex][1])
                        newTable.set(key, keyHash, val)
                        self.entries[entryIndex] = newTable
                        self.typeBitmap |= bitIndex
                        # logging.debug("---------- end set %r %d %r %d" % (key, keyHash, val, self.level))
            else: #we don't have an entry, rearrange our whole life
                # logging.debug("There's no entry here, need to add a new one at position %d" % entryIndex)
                self.entries.insert(entryIndex, (key, val))
                self.entryBitmap |= bitIndex
                # logging.debug("---------- end set %r %d %r %d" % (key, keyHash, val, self.level))

        def __str__(self):
            entryTuples = [(self.entries[HAMT.popcount(self.entryBitmap & ((1 << i) - 1))], 0 != self.typeBitmap & (1 << i)) \
                            for i in xrange(1 << HAMT.wordsize) if self.entryBitmap & (1 << i)]
            entriesList = ['{"entryType": "subTable", "contents": %s}' % entryTuple[0] \
                            if entryTuple[1] else \
                            '{"entryType": "keyValPair", "contents": {"key": "%s", "val": %d}}' % (entryTuple[0][0], entryTuple[0][1])
                            for entryTuple in entryTuples]
            entriesString = '[\n' + '\t' * (self.level + 1) + (',\n' + '\t' * (self.level + 1)).join(entriesList) + \
                            '\n' + '\t' * (self.level)+ ']'
            return '{\n%s"level": %d, \n%s"entryBitmap": "%s", \n%s"typeBitmap": "%s", \n%s"entries": %s}' % (
                '\t' * (self.level), self.level,
                '\t' * (self.level), bin(self.entryBitmap),
                '\t' * (self.level), bin(self.typeBitmap),
                '\t' * (self.level), entriesString
            )

    def __init__(self):
        self.root = self.NodeTable(0)

    def __getitem__(self, key):
        try:
            return self.root.get(key, self.hashfn(key))
        except KeyError:
            raise

    def __setitem__(self, key, val):
        self.root.set(key, self.hashfn(key), val)

    def __str__(self):
        return "%s" % self.root

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'native':
        worddict = {}
    else:
        worddict = HAMT()
    with open("/usr/share/dict/words") as f:
        words = [line.strip('\n') for line in f]
    ### testing with collisions
    words, native = words[:10], {}
    for i in xrange(1000):
        word = random.choice(words)
        try:
            worddict[word] = worddict[word] + 1
        except KeyError:
            worddict[word] = 1
        try:
            native[word] = native[word] + 1
        except KeyError:
            native[word] = 1

    for word in words:
        print "%s: HAMT %d, native %d" % (word, worddict[word], native[word])
    print "%s" % worddict
