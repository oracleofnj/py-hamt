import sys
import logging
import mmh3

class HAMT(object):
    # http://www.valuedlessons.com/2009/01/popcount-in-python-with-benchmarks.html
    # http://graphics.stanford.edu/~seander/bithacks.html#CountBitsSetTable
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    POPCOUNT_TABLE16 = [0] * 2**16
    for index in xrange(len(POPCOUNT_TABLE16)):
        POPCOUNT_TABLE16[index] = (index & 1) + POPCOUNT_TABLE16[index >> 1]

    @classmethod
    def popcount32_table16(cls, v):
        return (cls.POPCOUNT_TABLE16[ v        & 0xffff] +
                cls.POPCOUNT_TABLE16[(v >> 16) & 0xffff])

    @classmethod
    def popcount64_table16(cls, v):
        logging.debug("called with value %d" % v)
        return (cls.POPCOUNT_TABLE16[ v        & 0xffff] +
                cls.POPCOUNT_TABLE16[(v >> 16) & 0xffff] +
                cls.POPCOUNT_TABLE16[(v >> 32) & 0xffff] +
                cls.POPCOUNT_TABLE16[(v >> 48) & 0xffff])

    @staticmethod
    def hash64(v):
        return mmh3.hash64(v)[0]

    if sys.maxsize > 2 ** 32:
        popcount = popcount64_table16
        wordsize = 6
        hashfn = hash64
    else:
        popcount = popcount32_table16
        wordsize = 5
        hashfn = mmh3.hash
    hashmask = 2 ** wordsize - 1

    class NodeTable(object):
        def __init__(self, level):
            logging.debug("Creating new NodeTable with level %d" % level)
            self.level = level
            self.entryBitmap = 0
            self.typeBitmap = 0
            self.entries = []

        def get(self, key, keyHash):
            logging.debug("Looking for %r with hash %d in level %d" % (key, keyHash, self.level))
            logging.debug("entryBitmap is %s, typeBitmap is %s" % (bin(self.entryBitmap), bin(self.typeBitmap)))
            subhash = HAMT.hashmask & (keyHash >> (self.level * HAMT.wordsize))
            bitIndex = 1 << subhash
            logging.debug("Subhash is %d, bitIndex is %s" % (subhash, bin(bitIndex)))
            if self.entryBitmap & bitIndex: # we have an entry
                entryIndex = HAMT.popcount(self.entryBitmap & (bitIndex - 1))
                logging.debug("We have an entry, entryIndex is %d" % entryIndex)
                if self.typeBitmap & bitIndex: # it's a subtable
                    logging.debug("The entry is a subtable, delegating")
                    return self.entries[entryIndex].get(keyHash, key)
                else:
                    if key == self.entries[entryIndex][0]:
                        return self.entries[entryIndex][1]
                    else:
                        raise KeyError(key)
            else:
                raise KeyError(key)

        def set(self, key, keyHash, val):
            logging.debug("Setting value for %r with hash %d to %r in level %d" % (key, keyHash, val, self.level))
            logging.debug("entryBitmap is %s, typeBitmap is %s" % (bin(self.entryBitmap), bin(self.typeBitmap)))
            subhash = HAMT.hashmask & (keyHash >> (self.level * HAMT.wordsize))
            bitIndex = 1 << subhash
            entryIndex = HAMT.popcount(self.entryBitmap & (bitIndex - 1))
            logging.debug("Subhash is %d, bitIndex is %s, entryIndex is %d" % (subhash, bin(bitIndex), entryIndex))
            if self.entryBitmap & bitIndex: # we have an entry
                if self.typeBitmap & bitIndex: #it's a subtable
                    logging.debug("We have an entry and it's a subtable, delegating")
                    self.entries[entryIndex].set(keyHash, key, val)
                else: # not a subtable
                    logging.debug("We have an entry but it's not a subtable, existing key is %r" % self.entries[entryIndex][0])
                    if key == self.entries[entryIndex][0]: # existing key, new value
                        logging.debug("That's the same! replacing the tuple")
                        self.entries[entryIndex] = (key, val)
                    else: # subhash collision! make a new NodeTable
                        logging.debug("That's different! replacing the tuple with a new NodeTable with level %d" % self.level + 1)
                        newTable = self.NodeTable(self.level + 1)
                        newTable.set(self.entries[entryIndex][0], HAMT.hashfn(self.entries[entryIndex][0]), self.entries[entryIndex][1])
                        newTable.set(key, keyHash, val)
                        self.entries[entryIndex] = newTable
                        self.typeBitmap |= bitIndex
            else: #we don't have an entry, rearrange our whole life
                logging.debug("There's no entry here, need to add a new one at position %d" % entryIndex)
                self.entries.insert(entryIndex, (key, val))
                self.entryBitmap |= bitIndex

    def __init__(self):
        self.root = self.NodeTable(0)

    def get(self, key):
        try:
            return self.root.get(key, self.hashfn(key))
        except KeyError:
            raise

    def set(self, key, val):
        self.root.set(key, self.hashfn(key), val)

if __name__ == "__main__":
    foo = HAMT()
    foo.set("foo", "bar")
    print "**** FOO: %s " % foo.get("foo")
    foo.set("bar", "baz")
    print "**** BAR: %s " % foo.get("bar")
    print "**** FOO: %s " % foo.get("foo")
    foo.set("foo","baz")
    print "**** FOO: %s " % foo.get("foo")
    print "**** BAR: %s " % foo.get("bar")
    try:
        print "**** BAZ: %s " % foo.get("baz")
    except KeyError:
        print "**** BAZ: NO BAZ!"
