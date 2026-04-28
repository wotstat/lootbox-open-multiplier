import BigWorld, Keys
from gui.shared.gui_items.processors.loot_boxes import LootBoxOpenProcessor
from AccountCommands import RES_SUCCESS
from functools import partial
from constants import REQUEST_COOLDOWN


VERSION = '{{VERSION}}'
DEBUG_MODE = '{{DEBUG_MODE}}'

MAX_OPEN_COUNT_BY_REQUEST = 20

oldRequest = None
oldResponse = None
oldInit = None

def log(msg):
  print('[MOD_WOTSTAT_LOOTBOX_MUL] %s' % msg)
  
def debug(msg):
  if DEBUG_MODE:
    print('[MOD_WOTSTAT_LOOTBOX_MUL] %s' % msg)

def deepMerge(d1, d2):
  if isinstance(d1, dict) and isinstance(d2, dict):
    result = dict(d1)
    for k, v in d2.iteritems():
      if k in result:
        result[k] = deepMerge(result[k], v)
      else:
        result[k] = v
    return result
  elif isinstance(d1, list) and isinstance(d2, list):
    return d1 + d2
  elif isinstance(d1, (int, float)) and isinstance(d2, (int, float)):
    return d1 + d2
  else:
    return d2

def mergeExtData(extData1, extData2, openCount):
  # type: (dict, dict, int) -> dict
  
  res = {}

  res['usedLimits'] = extData1.get('usedLimits', []) + extData2.get('usedLimits', [None] * openCount)
  
  # openedLootBoxes
  openedLootBoxes1 = extData1.get('openedLootBoxes', {}) # {lootBoxID: count}
  openedLootBoxes2 = extData2.get('openedLootBoxes', {}) # {lootBoxID: count}
  
  for k, v in openedLootBoxes2.iteritems():
    if k in openedLootBoxes1: openedLootBoxes1[k] += v
    else: openedLootBoxes1[k] = v
      
  res['openedLootBoxes'] = openedLootBoxes1
  
  # startVerStat
  startVerStat1 = extData1.get('startVerStat', {}) # {verStatID: count}
  startVerStat2 = extData2.get('startVerStat', {}) # {verStatID: count}
  
  for k, v in startVerStat2.iteritems():
    if k not in startVerStat1: startVerStat1[k] = v
      
  res['startVerStat'] = startVerStat1
  
  # deep merge other fields
  for k, v in extData2.iteritems():
    if k not in ['usedLimits', 'openedLootBoxes', 'startVerStat']:
      log('Merging ExtData field "%s" with value %s' % (k, str(v)))
      res[k] = deepMerge(extData1.get(k), v)
  
  return res

def newInit(self, lootBoxItem, count=1, keyID=0):
  # type: (LootBoxOpenProcessor, object, int, int) -> None
  
  if(BigWorld.isKeyDown(Keys.KEY_LALT)):
    count = 20
      
  if(BigWorld.isKeyDown(Keys.KEY_LCONTROL)):
    count = 50
    
  if(BigWorld.isKeyDown(Keys.KEY_LSHIFT)):
    count = 100
    
  if(BigWorld.isKeyDown(Keys.KEY_LSHIFT) and BigWorld.isKeyDown(Keys.KEY_LALT)):
    count = 250
    
  count = min(count, lootBoxItem.getInventoryCount())
  debug('Init: lootBoxItem=%s, count=%d, keyID=%d' % (lootBoxItem, count, keyID))

  oldInit(self, lootBoxItem, count, keyID)
  self.targetCount = count
  self.alreadyOpenedCount = 0
  self.bonuses = []
  self.extData = {}
  
def newRequest(self, callback):
  # type: (LootBoxOpenProcessor, callable) -> None
  
  self._LootBoxOpenProcessor__count = min((self.targetCount - self.alreadyOpenedCount), MAX_OPEN_COUNT_BY_REQUEST)
  log('Request: count = %d' % self._LootBoxOpenProcessor__count)
  oldRequest(self, callback)

def newResponse(self, code, callback, errStr='', ctx=None):
  # type: (LootBoxOpenProcessor, int, callable, str, dict) -> None
  
  log('Response: code=%s, error=%s, ctx=%s' % (code, errStr, ctx))
  
  if code != RES_SUCCESS: return oldResponse(self, code, callback, errStr, ctx)
  
  self.alreadyOpenedCount += self._LootBoxOpenProcessor__count

  bonus = ctx.get('bonus', [])
  self.bonuses.extend(bonus)
  
  self.extData = mergeExtData(self.extData, ctx.get('extData', {}), self._LootBoxOpenProcessor__count)
  
  if self.alreadyOpenedCount == self.targetCount or len(bonus) == 0:
    debug('LootBoxOpenProcessorOpenResponse: all boxes opened')
    return oldResponse(self, code, callback, errStr, ctx={'bonus': self.bonuses, 'extData': self.extData})
  
  debug("LootBoxOpenProcessorOpenResponse: not all boxes opened, opening next %d boxes" % (self.targetCount - self.alreadyOpenedCount))
  BigWorld.callback(REQUEST_COOLDOWN.LOOTBOX, partial(self._request, callback))
  return None


def init():
  global oldInit, oldRequest, oldResponse
  
  oldInit = LootBoxOpenProcessor.__init__
  oldRequest = LootBoxOpenProcessor._request
  oldResponse = LootBoxOpenProcessor._response
  
  LootBoxOpenProcessor.__init__ = newInit
  LootBoxOpenProcessor._request = newRequest
  LootBoxOpenProcessor._response = newResponse
  
  log('[MOD_WOTSTAT_LOOTBOX_MUL] mod_wotstat_lootboxOpenMultiplier v%s loaded' % VERSION)

def fini():
  global oldInit, oldRequest, oldResponse
  
  if oldInit is not None:
    LootBoxOpenProcessor.__init__ = oldInit
    oldInit = None
    
  if oldRequest is not None:
    LootBoxOpenProcessor._request = oldRequest
    oldRequest = None
    
  if oldResponse is not None:
    LootBoxOpenProcessor._response = oldResponse
    oldResponse = None