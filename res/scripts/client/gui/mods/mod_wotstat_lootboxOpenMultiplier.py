# -*- coding: utf-8 -*-
import BigWorld, Keys
from frameworks.wulf import ViewStatus
from gui.Scaleform.Waiting import convertToResource, worker
from gui.Scaleform.framework.WaitingView import WaitingView
from gui.impl import backport
from gui.impl.dialogs.builders import SimpleDialogBuilder
from gui.impl.dialogs.dialogs import showSimple
from gui.impl.gen.view_models.constants.dialog_presets import DialogPresets
from gui.impl.pub.dialog_window import DialogButtons
from gui.shared.gui_items.processors.loot_boxes import LootBoxOpenProcessor
from gui_lootboxes.gui.impl.lobby.gui_lootboxes import lootboxes_short_stats_view
from gui_lootboxes.gui.impl.lobby.gui_lootboxes.lootboxes_storage import LootBoxesStorageView
from gui_lootboxes.gui.storage_context.context import States
from AccountCommands import RES_SUCCESS
from functools import partial
from constants import REQUEST_COOLDOWN
from th_async import th_async, th_await
from weakref import ref


VERSION = '{{VERSION}}'
DEBUG_MODE = '{{DEBUG_MODE}}'

MAX_OPEN_COUNT_BY_REQUEST = 20
EXTRA_COUNTS = (20, 50, 100, 250)
OPENING_WAITING = 'lootboxOpeninig'
UI_ASSET_URL = 'coui://gui/gameface/mods/wotstat/lootboxOpenMultiplier/'

oldRequest = None
oldResponse = None
oldInit = None
oldOpenLootBoxes = None
oldStatsModel = None
oldShowWaiting = None
openingProcessorRef = None
pendingConfirmation = None


class ExplicitCount(int):
  def __int__(self):
    # The native storage handler converts the count with int() before posting its event.
    return self

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
  
  if isinstance(count, ExplicitCount):
    count = int.__int__(count)
  else:
    alt = BigWorld.isKeyDown(Keys.KEY_LALT)
    if BigWorld.isKeyDown(Keys.KEY_LSHIFT):
      count = 250 if alt else 100
    elif BigWorld.isKeyDown(Keys.KEY_LCONTROL):
      count = 50
    elif alt:
      count = 20
    
  count = min(int(count), lootBoxItem.getInventoryCount())
  debug('Init: lootBoxItem=%s, count=%d, keyID=%d' % (lootBoxItem, count, keyID))

  oldInit(self, lootBoxItem, count, keyID)
  self.targetCount = count
  self.alreadyOpenedCount = 0
  self.bonuses = []
  self.extData = {}
  self.openingWaitingTask = None

def setOpeningProgress(view, processor):
  if isinstance(view, WaitingView) and view._isDAAPIInited():
    lootBoxID = processor._LootBoxOpenProcessor__lootBox.getID()
    openedCount = processor.extData.get('openedLootBoxes', {}).get(lootBoxID, processor.alreadyOpenedCount)
    message = backport.text(processor.openingWaitingTask.messageID).rstrip(u'.\u2026 ')
    setMessage = view.flashObject.waitingComponent.setMessage
    if setMessage.isObjectOrMethod:
      setMessage(u'%s %d/%d...' % (message, openedCount, processor.targetCount))

def updateOpeningProgress(self):
  global openingProcessorRef
  if self.targetCount <= 50:
    return

  waiting = worker()
  if self.openingWaitingTask is None:
    messageID = convertToResource(OPENING_WAITING)()
    self.openingWaitingTask = waiting.getWaitingTask(messageID) or waiting.getSuspendedWaitingTask(messageID)
    if self.openingWaitingTask is None:
      return
    openingProcessorRef = ref(self)

  stack = waiting.snapshort()['waiting']
  if stack and stack[-1] is self.openingWaitingTask:
    setOpeningProgress(waiting.getWaitingView(stack[-1].isBlocking), self)

def newShowWaiting(self, messageID, softStart=False):
  result = oldShowWaiting(self, messageID, softStart)
  processor = openingProcessorRef() if openingProcessorRef is not None else None
  if processor is not None and processor.openingWaitingTask.messageID == messageID:
    waiting = worker()
    task = processor.openingWaitingTask
    if task is waiting.getWaitingTask(messageID) or task is waiting.getSuspendedWaitingTask(messageID):
      setOpeningProgress(self, processor)
  return result

def newRequest(self, callback):
  # type: (LootBoxOpenProcessor, callable) -> None
  
  self._LootBoxOpenProcessor__count = min((self.targetCount - self.alreadyOpenedCount), MAX_OPEN_COUNT_BY_REQUEST)
  if self.openingWaitingTask is None:
    updateOpeningProgress(self)
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
  updateOpeningProgress(self)
  
  if self.alreadyOpenedCount == self.targetCount or len(bonus) == 0:
    debug('LootBoxOpenProcessorOpenResponse: all boxes opened')
    return oldResponse(self, code, callback, errStr, ctx={'bonus': self.bonuses, 'extData': self.extData})
  
  debug("LootBoxOpenProcessorOpenResponse: not all boxes opened, opening next %d boxes" % (self.targetCount - self.alreadyOpenedCount))
  BigWorld.callback(REQUEST_COOLDOWN.LOOTBOX, partial(self._request, callback))
  return None


def getSelectedLootBox(view, lootBoxID, count):
  if view.viewStatus != ViewStatus.LOADED:
    return None
  if view.viewModel.getCurrentState() != States.STORAGE_VIEWING or view.viewModel.getCurrentLootboxID() != lootBoxID:
    return None
  lootBox = view._LootBoxesStorageView__itemsCache.items.tokens.getLootBoxByID(lootBoxID)
  if lootBox and lootBox.isEnabled and not lootBox.getUnlockKeyIDs() and lootBox.getInventoryCount() >= count:
    return lootBox
  return None

def openSelectedCount(view, lootBox, count):
  return oldOpenLootBoxes(view, {'lootBoxID': lootBox.getID(), 'count': ExplicitCount(count)})

@th_async
def confirmOpenCount(view, lootBoxID, count):
  global pendingConfirmation
  pendingConfirmation = view
  try:
    builder = SimpleDialogBuilder()
    builder.setPreset(DialogPresets.WARNING)
    builder.setFormattedTitle((u'Открыть %d контейнеров?' % count).encode('utf-8'))
    duration = u'около 30 секунд' if count == 100 else u'больше 30 секунд'
    builder.setFormattedMessage((u'Открытие %d контейнеров может занять %s.' % (count, duration)).encode('utf-8'))
    builder.addButton(DialogButtons.SUBMIT, 0, False, rawLabel=u'Да'.encode('utf-8'))
    builder.addButton(DialogButtons.CANCEL, 0, True, rawLabel=u'Отмена'.encode('utf-8'))
    confirmed = yield th_await(showSimple(builder.build(view)))
    if confirmed:
      lootBox = getSelectedLootBox(view, lootBoxID, count)
      if lootBox:
        openSelectedCount(view, lootBox, count)
  finally:
    pendingConfirmation = None

def newOpenLootBoxes(self, args):
  if 'wotstatCount' not in args:
    return oldOpenLootBoxes(self, args)
  if pendingConfirmation is not None:
    return

  count = args.get('wotstatCount')
  lootBoxID = self.viewModel.getCurrentLootboxID()
  if count not in EXTRA_COUNTS or args.get('lootBoxID') != lootBoxID:
    return
  count = int(count)
  lootBox = getSelectedLootBox(self, lootBoxID, count)
  if not lootBox:
    return

  if count >= 100:
    confirmOpenCount(self, lootBoxID, count)
  else:
    openSelectedCount(self, lootBox, count)

def initStorageUI():
  global oldStatsModel, oldOpenLootBoxes
  try:
    from openwg_gameface import gf_mod_inject
  except ImportError:
    log('OpenWG.Gameface is required for the extra count buttons')
    return

  # OpenWG injects assets from subviews. The storage already has a stats subview.
  statsModel = lootboxes_short_stats_view.LootboxesShortStatsViewModel

  class StatsModelWithCountButtons(statsModel):
    __slots__ = ()

    def __init__(self):
      super(StatsModelWithCountButtons, self).__init__(properties=9)

    def _initialize(self):
      super(StatsModelWithCountButtons, self)._initialize()
      gf_mod_inject(self, 'wotstatLootboxOpenMultiplier', styles=[UI_ASSET_URL + 'counts.css'],
                    scripts=[UI_ASSET_URL + 'counts.js'])

  oldStatsModel = statsModel
  oldOpenLootBoxes = LootBoxesStorageView._LootBoxesStorageView__openLootBoxes
  lootboxes_short_stats_view.LootboxesShortStatsViewModel = StatsModelWithCountButtons
  LootBoxesStorageView._LootBoxesStorageView__openLootBoxes = newOpenLootBoxes

def init():
  global oldInit, oldRequest, oldResponse, oldShowWaiting
  if oldInit is not None:
    return
  
  oldInit = LootBoxOpenProcessor.__init__
  oldRequest = LootBoxOpenProcessor._request
  oldResponse = LootBoxOpenProcessor._response
  oldShowWaiting = WaitingView.showWaiting
  
  LootBoxOpenProcessor.__init__ = newInit
  LootBoxOpenProcessor._request = newRequest
  LootBoxOpenProcessor._response = newResponse
  WaitingView.showWaiting = newShowWaiting
  initStorageUI()
  
  log('[MOD_WOTSTAT_LOOTBOX_MUL] mod_wotstat_lootboxOpenMultiplier v%s loaded' % VERSION)

def fini():
  global oldInit, oldRequest, oldResponse, oldStatsModel, oldOpenLootBoxes
  global oldShowWaiting, openingProcessorRef

  if oldShowWaiting is not None:
    WaitingView.showWaiting = oldShowWaiting
    oldShowWaiting = None
    openingProcessorRef = None

  if oldStatsModel is not None:
    lootboxes_short_stats_view.LootboxesShortStatsViewModel = oldStatsModel
    oldStatsModel = None

  if oldOpenLootBoxes is not None:
    LootBoxesStorageView._LootBoxesStorageView__openLootBoxes = oldOpenLootBoxes
    oldOpenLootBoxes = None
  
  if oldInit is not None:
    LootBoxOpenProcessor.__init__ = oldInit
    oldInit = None
    
  if oldRequest is not None:
    LootBoxOpenProcessor._request = oldRequest
    oldRequest = None
    
  if oldResponse is not None:
    LootBoxOpenProcessor._response = oldResponse
    oldResponse = None
