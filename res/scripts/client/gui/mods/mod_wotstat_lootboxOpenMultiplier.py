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

def newInit(self, lootBoxItem, count=1, keyID=0):
  # type: (LootBoxOpenProcessor, object, int, int) -> None
  
  if(BigWorld.isKeyDown(Keys.KEY_LALT)):
    count = 20
      
  if(BigWorld.isKeyDown(Keys.KEY_LCONTROL)):
    count = 50
    
  if(BigWorld.isKeyDown(Keys.KEY_LSHIFT)):
    count = 100
    
  count = min(count, lootBoxItem.getInventoryCount())
  debug('Init: lootBoxItem=%s, count=%d, keyID=%d' % (lootBoxItem, count, keyID))
  
  # itemsCache.items.tokens.getLootBoxByID(320022).getInventoryCount()

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
  
  self.extData = deepMerge(self.extData, ctx.get('extData', {}))
  
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
  
  print('[MOD_WOTSTAT_LOOTBOX_MUL] mod_wotstat_lootboxOpenMultiplier v%s loaded' % VERSION)

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