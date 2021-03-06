#!/usr/bin/env python

# Written by Bram Cohen
# modified for multitracker by John Hoffman
# see LICENSE.txt for license information

import sys
import os
import shutil
import threading
import traceback
from BitTornado.BT1.makemetafile import make_meta_file
from BitTornado.Info import MetaInfo

try:
    from wxPython import wx
except ImportError:
    print 'wxPython is not installed or has not been installed properly.'
    sys.exit(1)

basepath = os.path.abspath(os.path.dirname(sys.argv[0]))

if sys.platform == 'win32':
    DROP_HERE = '(drop here)'
else:
    DROP_HERE = ''


wxEVT_INVOKE = wx.wxNewEventType()


def EVT_INVOKE(win, func):
    win.Connect(-1, -1, wxEVT_INVOKE, func)


class InvokeEvent(wx.wxPyEvent):
    def __init__(self, func, args, kwargs):
        super(InvokeEvent, self).__init__()
        self.SetEventType(wxEVT_INVOKE)
        self.func = func
        self.args = args
        self.kwargs = kwargs


class BasicDownloadInfo:
    def __init__(self, config, calls):
        self.config = config
        self.calls = calls

        self.uiflag = threading.Event()
        self.cancelflag = threading.Event()
        self.switchlock = threading.Lock()
        self.working = False
        self.queue = []
        wx.wxInitAllImageHandlers()
        self.thostselection = self.calls['getCurrentTHost']()
        self.thostselectnum = 0
        self.choices = None
        self.choices1 = None
        self.announce = ''
        self.announce_list = None

        self.windowStyle = wx.wxSYSTEM_MENU | wx.wxCAPTION | wx.wxMINIMIZE_BOX
        if self.config['stayontop']:
            self.windowStyle |= wx.wxSTAY_ON_TOP
        frame = wx.wxFrame(None, -1, 'T-Make', size=wx.wxSize(-1, -1),
                           style=self.windowStyle)
        self.frame = frame
        panel = wx.wxPanel(frame, -1)
        mainSizer = wx.wxBoxSizer(wx.wxVERTICAL)
        groupSizer = wx.wxFlexGridSizer(cols=1, vgap=0, hgap=0)
#        self.dropTarget = self.calls['newDropTarget']((200, 200))
        self.dropTarget = self.calls['newDropTarget']()
        self.dropTargetPtr = wx.wxStaticBitmap(panel, -1, self.dropTarget)
        self.calls['setDropTargetRefresh'](self.dropTargetPtr.Refresh)
        self.dropTargetWidth = self.dropTarget.GetWidth()
        wx.EVT_LEFT_DOWN(self.dropTargetPtr, self.dropTargetClick)
        wx.EVT_ENTER_WINDOW(self.dropTargetPtr,
                            self.calls['dropTargetHovered'])
        wx.EVT_LEAVE_WINDOW(self.dropTargetPtr,
                            self.calls['dropTargetUnhovered'])
        groupSizer.Add(self.dropTargetPtr, 0, wx.wxALIGN_CENTER)
        lowerSizer1 = wx.wxGridSizer(cols=6)
        dirlink = wx.wxStaticText(panel, -1, 'dir')
        dirlink.SetFont(wx.wxFont(7, wx.wxDEFAULT, wx.wxNORMAL, wx.wxNORMAL,
                                  True))
        dirlink.SetForegroundColour('blue')
        wx.EVT_LEFT_UP(dirlink, self.selectdir)
        lowerSizer1.Add(dirlink, -1, wx.wxALIGN_LEFT)
        lowerSizer1.Add(wx.wxStaticText(panel, -1, ''), -1, wx.wxALIGN_CENTER)
        lowerSizer1.Add(wx.wxStaticText(panel, -1, ''), -1, wx.wxALIGN_CENTER)
        lowerSizer1.Add(wx.wxStaticText(panel, -1, ''), -1, wx.wxALIGN_CENTER)
        lowerSizer1.Add(wx.wxStaticText(panel, -1, ''), -1, wx.wxALIGN_CENTER)
        filelink = wx.wxStaticText(panel, -1, 'file')
        filelink.SetFont(wx.wxFont(7, wx.wxDEFAULT, wx.wxNORMAL, wx.wxNORMAL,
                         True))
        filelink.SetForegroundColour('blue')
        wx.EVT_LEFT_UP(filelink, self.selectfile)
        lowerSizer1.Add(filelink, -1, wx.wxALIGN_RIGHT)

        groupSizer.Add(lowerSizer1, -1, wx.wxALIGN_CENTER)

        self.gauge = wx.wxGauge(panel, -1, range=1000,
                                style=wx.wxGA_HORIZONTAL, size=(-1, 15))
        groupSizer.Add(self.gauge, 0, wx.wxEXPAND)
        self.statustext = wx.wxStaticText(panel, -1, 'ready',
                                          style=wx.wxALIGN_CENTER |
                                          wx.wxST_NO_AUTORESIZE)
        self.statustext.SetFont(wx.wxFont(7, wx.wxDEFAULT, wx.wxNORMAL,
                                          wx.wxBOLD, False))
        groupSizer.Add(self.statustext, -1, wx.wxEXPAND)
        self.choices = wx.wxChoice(panel, -1, (-1, -1),
                                   (self.dropTargetWidth, -1), choices=[])
        self.choices.SetFont(wx.wxFont(7, wx.wxDEFAULT, wx.wxNORMAL,
                                       wx.wxNORMAL, False))
        wx.EVT_CHOICE(self.choices, -1, self.set_thost)
        groupSizer.Add(self.choices, 0, wx.wxEXPAND)
        cancellink = wx.wxStaticText(panel, -1, 'cancel')
        cancellink.SetFont(wx.wxFont(7, wx.wxDEFAULT, wx.wxNORMAL, wx.wxNORMAL,
                                     True))
        cancellink.SetForegroundColour('red')
        wx.EVT_LEFT_UP(cancellink, self.cancel)
        groupSizer.Add(cancellink, -1, wx.wxALIGN_CENTER)
        advlink = wx.wxStaticText(panel, -1, 'advanced')
        advlink.SetFont(wx.wxFont(7, wx.wxDEFAULT, wx.wxNORMAL, wx.wxNORMAL,
                                  True))
        advlink.SetForegroundColour('blue')
        wx.EVT_LEFT_UP(advlink, self.calls['switchToAdvanced'])
        groupSizer.Add(advlink, -1, wx.wxALIGN_CENTER)
        mainSizer.Add(groupSizer, 0, wx.wxALIGN_CENTER)

        self.refresh_thostlist()
        self._set_thost()

        if sys.platform == 'win32':
            self.dropTargetPtr.DragAcceptFiles(True)
            wx.EVT_DROP_FILES(self.dropTargetPtr, self.selectdrop)

#        border = wxBoxSizer(wxHORIZONTAL)
#        border.Add(mainSizer, 1, wxEXPAND | wxALL, 0)
        panel.SetSizer(mainSizer)
        panel.SetAutoLayout(True)
#        border.Fit(panel)
        mainSizer.Fit(panel)
        frame.Fit()
        frame.Show(True)

        EVT_INVOKE(frame, self.onInvoke)
        wx.EVT_CLOSE(frame, self._close)

    def selectdir(self, x=None):
        self.calls['dropTargetHovered']()
        dl = wx.wxDirDialog(
            self.frame, style=wx.wxDD_DEFAULT_STYLE | wx.wxDD_NEW_DIR_BUTTON)
        if dl.ShowModal() == wx.wxID_OK:
            self.calls['dropTargetDropped']()
            self.complete(dl.GetPath())
        else:
            self.calls['dropTargetUnhovered']()

    def selectfile(self, x=None):
        self.calls['dropTargetHovered']()
        dl = wx.wxFileDialog(self.frame, 'Choose file to use', '', '', '',
                             wx.wxOPEN)
        if dl.ShowModal() == wx.wxID_OK:
            self.calls['dropTargetDropped']()
            self.complete(dl.GetPath())
        else:
            self.calls['dropTargetUnhovered']()

    def selectdrop(self, dat):
        self.calls['dropTargetDropped']()
        for f in dat.GetFiles():
            self.complete(f)

    def _announcecopy(self, f):
        try:
            metainfo = MetaInfo.read(f)
            self.announce = metainfo['announce']
            self.announce_list = metainfo.get('announce-list')
        except:
            return

    def complete(self, x):
        params = {'piece_size_pow2': 0}
        if self.announce_list:
            params['real_announce_list'] = self.announce_list
        self.queue.append((x, self.announce, params))
        self.go_queue()

    def go_queue(self):
        self.switchlock.acquire()
        if self.queue and not self.working:
            self.working = True
            self.statustext.SetLabel('working')
            q = self.queue.pop(0)
            MakeMetafile(q[0], q[1], q[2], self)
        self.switchlock.release()

    def cancel(self, x):
        self.switchlock.acquire()
        if self.working:
            self.working = False
            self.cancelflag.set()
            self.cancelflag = threading.Event()
            self.queue = []
            self.statustext.SetLabel('CANCELED')
            self.calls['dropTargetError']()
        self.switchlock.release()

    def dropTargetClick(self, x):
        if x.GetPosition()[0] < int(self.dropTargetWidth * 0.4):
            self.selectdir()
        elif x.GetPosition()[0] > int(self.dropTargetWidth * 0.6):
            self.selectfile()

    def refresh_thostlist(self):
        l = []
        d = 0
        for f in os.listdir(os.path.join(basepath, 'thosts')):
            if f[-6:].lower() == '.thost':
                l.append(f)
                if f == self.thostselection:
                    d = len(l)
        self.choices.Clear()
        if not d:
            if l:
                self.thostselection = l[0]
                d = 1
            else:
                self.thostselection = ''
                d = 1
            self.config['thost'] = self.thostselection
            self.calls['saveConfig']()
        for f in l:
            self.choices.Append(f[:-6])
        self.thostselectnum = d - 1
        self.thostlist = l
        self.choices.SetSelection(d - 1)
        return

    def set_thost(self, x):
        n = self.choices.GetSelection()
        if n != self.thostselectnum:
            self.thostselectnum = n
            if n:
                self.thostselection = self.thostlist[n - 1]

    def _set_thost(self):
        self._announcecopy(os.path.join(basepath, 'thosts',
                                        self.thostselection))
        self.calls['setCurrentTHost'](self.thostselection)

    def onInvoke(self, event):
        if not self.uiflag.isSet():
            apply(event.func, event.args, event.kwargs)

    def invokeLater(self, func, args=[], kwargs={}):
        if not self.uiflag.isSet():
            wx.wxPostEvent(self.frame, InvokeEvent(func, args, kwargs))

    def build_setgauge(self, x):
        self.invokeLater(self.on_setgauge, [x])

    def on_setgauge(self, x):
        self.gauge.SetValue(int(x * 1000))

    def build_done(self):
        self.invokeLater(self.on_builddone)

    def on_builddone(self):
        self.gauge.SetValue(0)
        self.statustext.SetLabel('done!')
        self.calls['dropTargetSuccess']()
        self.working = False
        self.go_queue()

    def build_failed(self, e):
        self.invokeLater(self.on_buildfailed, [e])

    def on_buildfailed(self, e):
        self.gauge.SetValue(0)
        self.statustext.SetLabel('ERROR')
        self.calls['dropTargetError']()
        self.working = False
        self.go_queue()

    def close(self):
        self.cancelflag = None   # this is a planned switch, don't cancel
        self.uiflag.set()
        self.frame.Close()

    def _close(self, x=None):
        self.uiflag.set()
        try:
            self.cancelflag.set()
        except:
            pass
        self.frame.Destroy()


class AdvancedDownloadInfo:
    def __init__(self, config, calls):
        self.config = config
        self.calls = calls

        self.uiflag = threading.Event()
        self.cancelflag = threading.Event()
        self.switchlock = threading.Lock()
        self.working = False
        self.queue = []
        wx.wxInitAllImageHandlers()
        self.thostselection = self.calls['getCurrentTHost']()
        self.thostselectnum = 0
        self.choices = None
        self.choices1 = None

        self.windowStyle = wx.wxSYSTEM_MENU | wx.wxCAPTION | wx.wxMINIMIZE_BOX
        if self.config['stayontop']:
            self.windowStyle |= wx.wxSTAY_ON_TOP
        frame = wx.wxFrame(None, -1, 'T-Make',
                           size=wx.wxSize(-1, -1), style=self.windowStyle)
        self.frame = frame
        panel = wx.wxPanel(frame, -1)

        fullSizer = wx.wxFlexGridSizer(cols=1, vgap=0, hgap=8)

        colSizer = wx.wxFlexGridSizer(cols=2, vgap=0, hgap=8)
        leftSizer = wx.wxFlexGridSizer(cols=1, vgap=3)

        self.stayontop_checkbox = wx.wxCheckBox(panel, -1, "stay on top")
        self.stayontop_checkbox.SetValue(self.config['stayontop'])
        wx.EVT_CHECKBOX(frame, self.stayontop_checkbox.GetId(),
                        self.setstayontop)
        leftSizer.Add(self.stayontop_checkbox, -1, wx.wxALIGN_CENTER)
        leftSizer.Add(wx.wxStaticText(panel, -1, ''))

        button = wx.wxButton(panel, -1, 'use image...')
        wx.EVT_BUTTON(frame, button.GetId(), self.selectDropTarget)
        leftSizer.Add(button, -1, wx.wxALIGN_CENTER)

        self.groupSizer1Box = wx.wxStaticBox(panel, -1, '')
        groupSizer1 = wx.wxStaticBoxSizer(self.groupSizer1Box, wx.wxHORIZONTAL)
        groupSizer = wx.wxFlexGridSizer(cols=1, vgap=0)
        self.dropTarget = self.calls['newDropTarget']((200, 200))
#        self.dropTarget = self.calls['newDropTarget']()
        self.dropTargetPtr = wx.wxStaticBitmap(panel, -1, self.dropTarget)
        self.calls['setDropTargetRefresh'](self.dropTargetPtr.Refresh)
        self.dropTargetWidth = self.dropTarget.GetWidth()
        wx.EVT_LEFT_DOWN(self.dropTargetPtr, self.dropTargetClick)
        wx.EVT_ENTER_WINDOW(self.dropTargetPtr,
                            self.calls['dropTargetHovered'])
        wx.EVT_LEAVE_WINDOW(self.dropTargetPtr,
                            self.calls['dropTargetUnhovered'])
        groupSizer.Add(self.dropTargetPtr, 0, wx.wxALIGN_CENTER)
        lowerSizer1 = wx.wxGridSizer(cols=3)
        dirlink = wx.wxStaticText(panel, -1, 'dir')
        dirlink.SetFont(wx.wxFont(7, wx.wxDEFAULT, wx.wxNORMAL, wx.wxNORMAL,
                                  True))
        dirlink.SetForegroundColour('blue')
        wx.EVT_LEFT_UP(dirlink, self.selectdir)
        lowerSizer1.Add(dirlink, -1, wx.wxALIGN_LEFT)
        lowerSizer1.Add(wx.wxStaticText(panel, -1, ''), -1, wx.wxALIGN_CENTER)
        filelink = wx.wxStaticText(panel, -1, 'file')
        filelink.SetFont(wx.wxFont(7, wx.wxDEFAULT, wx.wxNORMAL, wx.wxNORMAL,
                                   True))
        filelink.SetForegroundColour('blue')
        wx.EVT_LEFT_UP(filelink, self.selectfile)
        lowerSizer1.Add(filelink, -1, wx.wxALIGN_RIGHT)

        groupSizer.Add(lowerSizer1, -1, wx.wxALIGN_CENTER)

        self.gauge = wx.wxGauge(panel, -1, range=1000,
                                style=wx.wxGA_HORIZONTAL, size=(-1, 15))
        groupSizer.Add(self.gauge, 0, wx.wxEXPAND)
        self.statustext = wx.wxStaticText(
            panel, -1, 'ready',
            style=wx.wxALIGN_CENTER | wx.wxST_NO_AUTORESIZE)
        self.statustext.SetFont(wx.wxFont(7, wx.wxDEFAULT, wx.wxNORMAL,
                                          wx.wxBOLD, False))
        groupSizer.Add(self.statustext, -1, wx.wxEXPAND)
        self.choices = wx.wxChoice(panel, -1, (-1, -1),
                                   (self.dropTargetWidth, -1), choices=[])
        self.choices.SetFont(wx.wxFont(7, wx.wxDEFAULT, wx.wxNORMAL,
                                       wx.wxNORMAL, False))
        wx.EVT_CHOICE(self.choices, -1, self.set_thost)
        groupSizer.Add(self.choices, 0, wx.wxEXPAND)
        cancellink = wx.wxStaticText(panel, -1, 'cancel')
        cancellink.SetFont(wx.wxFont(7, wx.wxDEFAULT, wx.wxNORMAL, wx.wxNORMAL,
                                     True))
        cancellink.SetForegroundColour('red')
        wx.EVT_LEFT_UP(cancellink, self.cancel)
        groupSizer.Add(cancellink, -1, wx.wxALIGN_CENTER)
        dummyadvlink = wx.wxStaticText(panel, -1, 'advanced')
        dummyadvlink.SetFont(wx.wxFont(7, wx.wxDEFAULT, wx.wxNORMAL,
                                       wx.wxNORMAL, False))
        dummyadvlink.SetForegroundColour('blue')
        wx.EVT_LEFT_UP(dirlink, self.selectdir)
        groupSizer.Add(dummyadvlink, -1, wx.wxALIGN_CENTER)
        groupSizer1.Add(groupSizer)
        leftSizer.Add(groupSizer1, -1, wx.wxALIGN_CENTER)

        leftSizer.Add(wx.wxStaticText(panel, -1, 'make torrent of:'), 0,
                      wx.wxALIGN_CENTER)

        self.dirCtl = wx.wxTextCtrl(panel, -1, '', size=(250, -1))
        leftSizer.Add(self.dirCtl, 1, wx.wxEXPAND)

        b = wx.wxBoxSizer(wx.wxHORIZONTAL)
        button = wx.wxButton(panel, -1, 'dir')
        wx.EVT_BUTTON(frame, button.GetId(), self.selectdir)
        b.Add(button, 0)

        button2 = wx.wxButton(panel, -1, 'file')
        wx.EVT_BUTTON(frame, button2.GetId(), self.selectfile)
        b.Add(button2, 0)

        leftSizer.Add(b, 0, wx.wxALIGN_CENTER)

        leftSizer.Add(wx.wxStaticText(panel, -1, ''))

        simple_link = wx.wxStaticText(panel, -1, 'back to basic mode')
        simple_link.SetFont(wx.wxFont(-1, wx.wxDEFAULT, wx.wxNORMAL,
                                      wx.wxNORMAL, True))
        simple_link.SetForegroundColour('blue')
        wx.EVT_LEFT_UP(simple_link, self.calls['switchToBasic'])
        leftSizer.Add(simple_link, -1, wx.wxALIGN_CENTER)

        colSizer.Add(leftSizer, -1, wx.wxALIGN_CENTER_VERTICAL)

        gridSizer = wx.wxFlexGridSizer(cols=2, vgap=6, hgap=8)

        gridSizer.Add(wx.wxStaticText(panel, -1, 'Torrent host:'), -1,
                      wx.wxALIGN_RIGHT | wx.wxALIGN_CENTER_VERTICAL)

        self.choices1 = wx.wxChoice(panel, -1, (-1, -1), (-1, -1),
                                    choices=[])
        wx.EVT_CHOICE(self.choices1, -1, self.set_thost1)
        gridSizer.Add(self.choices1, 0, wx.wxEXPAND)

        b = wx.wxBoxSizer(wx.wxHORIZONTAL)
        button1 = wx.wxButton(panel, -1, 'set default')
        wx.EVT_BUTTON(frame, button1.GetId(), self.set_default_thost)
        b.Add(button1, 0)
        b.Add(wx.wxStaticText(panel, -1, '       '))
        button2 = wx.wxButton(panel, -1, 'delete')
        wx.EVT_BUTTON(frame, button2.GetId(), self.delete_thost)
        b.Add(button2, 0)
        b.Add(wx.wxStaticText(panel, -1, '       '))
        button3 = wx.wxButton(panel, -1, 'save as...')
        wx.EVT_BUTTON(frame, button3.GetId(), self.save_thost)
        b.Add(button3, 0)

        gridSizer.Add(wx.wxStaticText(panel, -1, ''))
        gridSizer.Add(b, 0, wx.wxALIGN_CENTER)

        gridSizer.Add(wx.wxStaticText(panel, -1, ''))
        gridSizer.Add(wx.wxStaticText(panel, -1, ''))

        gridSizer.Add(wx.wxStaticText(panel, -1, 'single tracker url:'), 0,
                      wx.wxALIGN_RIGHT | wx.wxALIGN_CENTER_VERTICAL)
        self.annCtl = wx.wxTextCtrl(panel, -1,
                                    'http://my.tracker:6969/announce')
        gridSizer.Add(self.annCtl, 0, wx.wxEXPAND)

        a = wx.wxFlexGridSizer(cols=1, vgap=3)
        a.Add(wx.wxStaticText(panel, -1, 'tracker list:'), 0, wx.wxALIGN_RIGHT)
        a.Add(wx.wxStaticText(panel, -1, ''))
        abutton = wx.wxButton(panel, -1, 'copy\nannounces\nfrom\ntorrent',
                              size=(70, 70))
        wx.EVT_BUTTON(frame, abutton.GetId(), self.announcecopy)
        a.Add(abutton, -1, wx.wxALIGN_CENTER)
        a.Add(wx.wxStaticText(panel, -1, DROP_HERE), -1, wx.wxALIGN_CENTER)
        gridSizer.Add(a, -1, wx.wxALIGN_RIGHT | wx.wxALIGN_CENTER_VERTICAL)

        self.annListCtl = wx.wxTextCtrl(
            panel, -1, '\n\n\n\n\n', wx.wxPoint(-1, -1), (300, 120),
            wx.wxTE_MULTILINE | wx.wxHSCROLL | wx.wxTE_DONTWRAP)
        gridSizer.Add(self.annListCtl, -1, wx.wxEXPAND)

        gridSizer.Add(wx.wxStaticText(panel, -1, ''))
        exptext = wx.wxStaticText(
            panel, -1, 'a list of tracker urls separated by commas or '
            'whitespace\nand on several lines -trackers on the same line will '
            'be\ntried randomly, and all the trackers on one line\nwill be '
            'tried before the trackers on the next line.')
        exptext.SetFont(wx.wxFont(6, wx.wxDEFAULT, wx.wxNORMAL, wx.wxNORMAL,
                                  False))
        gridSizer.Add(exptext, -1, wx.wxALIGN_CENTER)

        self.refresh_thostlist()
        self._set_thost()

        if sys.platform == 'win32':
            self.dropTargetPtr.DragAcceptFiles(True)
            wx.EVT_DROP_FILES(self.dropTargetPtr, self.selectdrop)
            self.groupSizer1Box.DragAcceptFiles(True)
            wx.EVT_DROP_FILES(self.groupSizer1Box, self.selectdrop)
            abutton.DragAcceptFiles(True)
            wx.EVT_DROP_FILES(abutton, self.announcedrop)
            self.annCtl.DragAcceptFiles(True)
            wx.EVT_DROP_FILES(self.annCtl, self.announcedrop)
            self.annListCtl.DragAcceptFiles(True)
            wx.EVT_DROP_FILES(self.annListCtl, self.announcedrop)

        gridSizer.Add(wx.wxStaticText(panel, -1, ''))
        gridSizer.Add(wx.wxStaticText(panel, -1, ''))

        gridSizer.Add(wx.wxStaticText(panel, -1, 'piece size:'), 0,
                      wx.wxALIGN_RIGHT | wx.wxALIGN_CENTER_VERTICAL)
        self.piece_length = wx.wxChoice(
            panel, -1, choices=['automatic', '2MiB', '1MiB', '512KiB',
                                '256KiB', '128KiB', '64KiB', '32KiB'])
        self.piece_length_list = [0, 21, 20, 19, 18, 17, 16, 15]
        self.piece_length.SetSelection(0)
        gridSizer.Add(self.piece_length)

        gridSizer.Add(wx.wxStaticText(panel, -1, 'comment:'), 0,
                      wx.wxALIGN_RIGHT | wx.wxALIGN_CENTER_VERTICAL)
        self.commentCtl = wx.wxTextCtrl(panel, -1, '')
        gridSizer.Add(self.commentCtl, 0, wx.wxEXPAND)

        gridSizer.Add(wx.wxStaticText(panel, -1, ''))
        gridSizer.Add(wx.wxStaticText(panel, -1, ''))

        b1 = wx.wxButton(panel, -1, 'Cancel', size=(-1, 30))
        wx.EVT_BUTTON(frame, b1.GetId(), self.cancel)
        gridSizer.Add(b1, 0, wx.wxEXPAND)
        b2 = wx.wxButton(panel, -1, 'MAKE TORRENT', size=(-1, 30))
        wx.EVT_BUTTON(frame, b2.GetId(), self.complete)
        gridSizer.Add(b2, 0, wx.wxEXPAND)

        gridSizer.AddGrowableCol(1)
        colSizer.Add(gridSizer, -1, wx.wxALIGN_CENTER_VERTICAL)
        fullSizer.Add(colSizer)

        border = wx.wxBoxSizer(wx.wxHORIZONTAL)
        border.Add(fullSizer, 1, wx.wxEXPAND | wx.wxALL, 15)
        panel.SetSizer(border)
        panel.SetAutoLayout(True)
        border.Fit(panel)
        frame.Fit()
        frame.Show(True)

        EVT_INVOKE(frame, self.onInvoke)
        wx.EVT_CLOSE(frame, self._close)

    def setstayontop(self, x):
        if self.stayontop_checkbox.GetValue():
            self.windowStyle |= wx.wxSTAY_ON_TOP
        else:
            self.windowStyle &= ~wx.wxSTAY_ON_TOP
        self.frame.SetWindowStyle(self.windowStyle)
        self.config['stayontop'] = self.stayontop_checkbox.GetValue()

    def selectdir(self, x=None):
        self.calls['dropTargetHovered']()
        dl = wx.wxDirDialog(
            self.frame, style=wx.wxDD_DEFAULT_STYLE | wx.wxDD_NEW_DIR_BUTTON)
        if dl.ShowModal() == wx.wxID_OK:
            self.dirCtl.SetValue(dl.GetPath())
            self.calls['dropTargetDropped']()
        else:
            self.calls['dropTargetUnhovered']()

    def selectfile(self, x=None):
        self.calls['dropTargetHovered']()
        dl = wx.wxFileDialog(self.frame, 'Choose file to use', '', '', '',
                             wx.wxOPEN)
        if dl.ShowModal() == wx.wxID_OK:
            self.dirCtl.SetValue(dl.GetPath())
            self.calls['dropTargetDropped']()
        else:
            self.calls['dropTargetUnhovered']()

    def selectdrop(self, dat):
        self.calls['dropTargetDropped']()
        for f in dat.GetFiles():
            self.complete(f)

    def announcecopy(self, x):
        dl = wx.wxFileDialog(self.frame, 'Choose .torrent file to use', '',
                             '', '*.torrent', wx.wxOPEN)
        if dl.ShowModal() == wx.wxID_OK:
            self._announcecopy(dl.GetPath(), True)

    def announcedrop(self, dat):
        self._announcecopy(dat.GetFiles()[0], True)

    def _announcecopy(self, f, external=False):
        try:
            metainfo = MetaInfo.read(f)
            self.annCtl.SetValue(metainfo['announce'])
            if 'announce-list' in metainfo:
                self.annListCtl.SetValue('\n'.join(', '.join(tier)
                                         for tier in metainfo['announce-list'])
                                         + '\n' * 3)
            else:
                self.annListCtl.SetValue('')
            if external:
                self.choices.SetSelection(0)
                self.choices1.SetSelection(0)
        except:
            return

    def getannouncelist(self):
        annList = filter(bool, self.annListCtl.GetValue().split('\n'))
        return [filter(bool, tier.replace(', ', ' ').split())
                for tier in annList]

    def complete(self, x):
        if not self.dirCtl.GetValue():
            dlg = wx.wxMessageDialog(
                self.frame, message='You must select a\nfile or directory',
                caption='Error', style=wx.wxOK | wx.wxICON_ERROR)
            dlg.ShowModal()
            dlg.Destroy()
            return
        if not self.annCtl.GetValue():
            dlg = wx.wxMessageDialog(
                self.frame, message='You must specify a\nsingle tracker url',
                caption='Error', style=wx.wxOK | wx.wxICON_ERROR)
            dlg.ShowModal()
            dlg.Destroy()
            return
        params = {'piece_size_pow2':
                  self.piece_length_list[self.piece_length.GetSelection()]}
        annlist = self.getannouncelist()
        if len(annlist) > 0:
            warnings = ''
            for tier in annlist:
                if len(tier) > 1:
                    warnings += (
                        'WARNING: You should not specify multiple trackers\n' +
                        '     on the same line of the tracker list unless\n' +
                        '     you are certain they share peer data.\n')
                    break
            if not self.annCtl.GetValue() in annlist[0]:
                    warnings += (
                        'WARNING: The single tracker url is not present in\n' +
                        '     the first line of the tracker list.  This\n' +
                        '     may produce a dysfunctional torrent.\n')
            if warnings:
                warnings += ('Are you sure you wish to produce a .torrent\n' +
                             'with these parameters?')
                dlg = wx.wxMessageDialog(
                    self.frame, message=warnings, caption='Warning',
                    style=wx.wxYES_NO | wx.wxICON_QUESTION)
                if dlg.ShowModal() != wx.wxID_YES:
                    dlg.Destroy()
                    return
            params['real_announce_list'] = annlist
        comment = self.commentCtl.GetValue()
        if comment != '':
            params['comment'] = comment
        self.statustext.SetLabel('working')
        self.queue.append((self.dirCtl.GetValue(), self.annCtl.GetValue(),
                           params))
        self.go_queue()

    def go_queue(self):
        self.switchlock.acquire()
        if self.queue and not self.working:
            self.working = True
            self.statustext.SetLabel('working')
            q = self.queue.pop(0)
            MakeMetafile(q[0], q[1], q[2], self)
        self.switchlock.release()

    def cancel(self, x):
        self.switchlock.acquire()
        if self.working:
            self.working = False
            self.cancelflag.set()
            self.cancelflag = threading.Event()
            self.queue = []
            self.statustext.SetLabel('CANCELED')
            self.calls['dropTargetError']()
        self.switchlock.release()

    def selectDropTarget(self, x):
        dl = wx.wxFileDialog(self.frame, 'Choose image to use',
                             os.path.join(basepath, 'targets'),
                             os.path.join(basepath, 'targets',
                                          self.config['target']),
                             'Supported images (*.bmp, *.gif)|*.*',
                             wx.wxOPEN | wx.wxHIDE_READONLY)
        if dl.ShowModal() == wx.wxID_OK:
            try:
                self.calls['changeDropTarget'](dl.GetPath())
                self.config['target'] = dl.GetPath()
            except:
                pass

    def dropTargetClick(self, x):
        if x.GetPosition()[0] < int(self.dropTargetWidth * 0.4):
            self.selectdir()
        elif x.GetPosition()[0] > int(self.dropTargetWidth * 0.6):
            self.selectfile()

    def refresh_thostlist(self):
        l = []
        d = 0
        for f in os.listdir(os.path.join(basepath, 'thosts')):
            if f[-6:].lower() == '.thost':
                l.append(f)
                if f == self.thostselection:
                    d = len(l)
        self.choices.Clear()
        self.choices.Append(' ')
        self.choices1.Clear()
        self.choices1.Append('---')
        if not d:
            if l:
                self.thostselection = l[0]
                d = 1
            else:
                self.thostselection = ''
                d = 0
            self.config['thost'] = self.thostselection
        for f in l:
            f1 = f[:-6]
            self.choices.Append(f1)
            if f == self.config['thost']:
                f1 += ' (default)'
            self.choices1.Append(f1)
        self.thostselectnum = d
        self.thostlist = l
        self.choices.SetSelection(d)
        self.choices1.SetSelection(d)

    def set_thost(self, x):
        n = self.choices.GetSelection()
        if n != self.thostselectnum:
            self.thostselectnum = n
            self.choices1.SetSelection(n)
            if n:
                self.thostselection = self.thostlist[n - 1]
                self._set_thost()

    def set_thost1(self, x):
        n = self.choices1.GetSelection()
        if n != self.thostselectnum:
            self.thostselectnum = n
            self.choices.SetSelection(n)
            if n:
                self.thostselection = self.thostlist[n - 1]
                self._set_thost()

    def _set_thost(self):
        self._announcecopy(os.path.join(basepath, 'thosts',
                                        self.thostselection))
        self.calls['setCurrentTHost'](self.thostselection)

    def set_default_thost(self, x):
        if self.thostlist:
            self.config['thost'] = self.thostselection
            self.refresh_thostlist()

    def save_thost(self, x):
        if not self.annCtl.GetValue():
            dlg = wx.wxMessageDialog(
                self.frame, message='You must specify a\nsingle tracker url',
                caption='Error', style=wx.wxOK | wx.wxICON_ERROR)
            dlg.ShowModal()
            dlg.Destroy()
            return
        try:
            metainfo = {}
            metainfo['announce'] = self.annCtl.GetValue()
            annlist = self.getannouncelist()
            if len(annlist) > 0:
                warnings = ''
                for tier in annlist:
                    if len(tier) > 1:
                        warnings += 'WARNING: You should not specify ' \
                            'multiple trackers\n     on the same line of ' \
                            'the tracker list unless\n     you are certain ' \
                            'they share peer data.\n'
                        break
                if not self.annCtl.GetValue() in annlist[0]:
                        warnings += 'WARNING: The single tracker url is not ' \
                            'present in\n     the first line of the tracker ' \
                            'list.  This\n     may produce a dysfunctional ' \
                            'torrent.\n'
                if warnings:
                    warnings += 'Are you sure you wish to save a torrent ' \
                        'host\nwith these parameters?'
                    dlg = wx.wxMessageDialog(
                        self.frame, message=warnings, caption='Warning',
                        style=wx.wxYES_NO | wx.wxICON_QUESTION)
                    if dlg.ShowModal() != wx.wxID_YES:
                        dlg.Destroy()
                        return
                metainfo['announce-list'] = annlist
        except:
            return

        if self.thostselectnum:
            d = self.thostselection
        else:
            d = '.thost'
        dl = wx.wxFileDialog(self.frame, 'Save tracker data as',
                             os.path.join(basepath, 'thosts'), d, '*.thost',
                             wx.wxSAVE | wx.wxOVERWRITE_PROMPT)
        if dl.ShowModal() != wx.wxID_OK:
            return
        d = dl.GetPath()

        try:
            metainfo.write(d)
            garbage, self.thostselection = os.path.split(d)
        except:
            pass
        self.refresh_thostlist()

    def delete_thost(self, x):
        dlg = wx.wxMessageDialog(
            self.frame, message='Are you sure you want to delete\n' +
            self.thostselection[:-6] + '?', caption='Warning',
            style=wx.wxYES_NO | wx.wxICON_EXCLAMATION)
        if dlg.ShowModal() != wx.wxID_YES:
            dlg.Destroy()
            return
        dlg.Destroy()
        os.remove(os.path.join(basepath, 'thosts', self.thostselection))
        self.thostselection = None
        self.refresh_thostlist()

    def onInvoke(self, event):
        if not self.uiflag.isSet():
            apply(event.func, event.args, event.kwargs)

    def invokeLater(self, func, args=[], kwargs={}):
        if not self.uiflag.isSet():
            wx.wxPostEvent(self.frame, InvokeEvent(func, args, kwargs))

    def build_setgauge(self, x):
        self.invokeLater(self.on_setgauge, [x])

    def on_setgauge(self, x):
        self.gauge.SetValue(int(x * 1000))

    def build_done(self):
        self.invokeLater(self.on_builddone)

    def on_builddone(self):
        self.gauge.SetValue(0)
        self.statustext.SetLabel('done!')
        self.calls['dropTargetSuccess']()
        self.working = False
        self.go_queue()

    def build_failed(self, e):
        self.invokeLater(self.on_buildfailed, [e])

    def on_buildfailed(self, e):
        self.gauge.SetValue(0)
        self.statustext.SetLabel('ERROR')
        self.calls['dropTargetError']()
        self.working = False
        self.go_queue()

    def close(self):
        self.cancelflag = None   # this is a planned switch, don't cancel
        self.uiflag.set()
        self.frame.Close()

    def _close(self, x=None):
        self.uiflag.set()
        try:
            self.cancelflag.set()
        except:
            pass
        self.calls['saveConfig']()
        self.frame.Destroy()


class MakeMetafile:
    def __init__(self, d, a, params, external=None):
        self.d = d
        self.a = a
        self.params = params

        self.call = external
#        self.uiflag = external.uiflag
        self.uiflag = external.cancelflag
        threading.Thread(target=self.complete).start()

    def complete(self):
        try:
            make_meta_file(self.d, self.a, self.params, self.uiflag,
                           self.call.build_setgauge, progress_percent=1)
            if not self.uiflag.isSet():
                self.call.build_done()
        except (OSError, IOError) as e:
            self.failed(e)
        except Exception as e:
            traceback.print_exc()
            self.failed(e)

    def failed(self, e):
        e = str(e)
        self.call.build_failed(e)
        dlg = wx.wxMessageDialog(self.frame, message='Error - ' + e,
                                 caption='Error',
                                 style=wx.wxOK | wx.wxICON_ERROR)
        dlg.ShowModal()
        dlg.Destroy()


class T_make:
    def __init__(self):
        self.configobj = wx.wxConfig('BitTorrent_T-make',
                                     style=wx.wxCONFIG_USE_LOCAL_FILE)
        self.getConfig()
        self.currentTHost = self.config['thost']
#        self.d = AdvancedDownloadInfo(self.config, self.getCalls())
        self.d = BasicDownloadInfo(self.config, self.getCalls())

    def getConfig(self):
        config = {}
        try:
            config['stayontop'] = self.configobj.ReadInt('stayontop', True)
        except:
            config['stayontop'] = True
            self.configobj.WriteInt('stayontop', True)
        try:
            config['target'] = self.configobj.Read('target', 'default.gif')
        except:
            config['target'] = 'default.gif'
            self.configobj.Write('target', 'default.gif')
        try:
            config['thost'] = self.configobj.Read('thost', '')
        except:
            config['thost'] = ''
            self.configobj.Write('thost', '')
        self.configobj.Flush()
        self.config = config

    def saveConfig(self):
        self.configobj.WriteInt('stayontop', self.config['stayontop'])
        self.configobj.Write('target', self.config['target'])
        self.configobj.Write('thost', self.config['thost'])
        self.configobj.Flush()

    def getCalls(self):
        calls = {}
        calls['saveConfig'] = self.saveConfig
        calls['newDropTarget'] = self.newDropTarget
        calls['setDropTargetRefresh'] = self.setDropTargetRefresh
        calls['changeDropTarget'] = self.changeDropTarget
        calls['setCurrentTHost'] = self.setCurrentTHost
        calls['getCurrentTHost'] = self.getCurrentTHost
        calls['dropTargetHovered'] = self.dropTargetHovered
        calls['dropTargetUnhovered'] = self.dropTargetUnhovered
        calls['dropTargetDropped'] = self.dropTargetDropped
        calls['dropTargetSuccess'] = self.dropTargetSuccess
        calls['dropTargetError'] = self.dropTargetError
        calls['switchToBasic'] = self.switchToBasic
        calls['switchToAdvanced'] = self.switchToAdvanced
        return calls

    def setCurrentTHost(self, x):
        self.currentTHost = x

    def getCurrentTHost(self):
        return self.currentTHost

    def newDropTarget(self, wh=None):
        if wh:
            self.dropTarget = wx.wxEmptyBitmap(wh[0], wh[1])
            try:
                self.changeDropTarget(self.config['target'])
            except:
                pass
        else:
            try:
                self.dropTarget = self._dropTargetRead(self.config['target'])
            except:
                try:
                    self.dropTarget = self._dropTargetRead('default.gif')
                    self.config['target'] = 'default.gif'
                    self.saveConfig()
                except:
                    self.dropTarget = wx.wxEmptyBitmap(100, 100)
        return self.dropTarget

    def setDropTargetRefresh(self, refreshfunc):
        self.dropTargetRefresh = refreshfunc

    def changeDropTarget(self, new):
        bmp = self._dropTargetRead(new)
        w1, h1 = self.dropTarget.GetWidth(), self.dropTarget.GetHeight()
        w, h = bmp.GetWidth(), bmp.GetHeight()
        x1, y1 = int((w1 - w) / 2.0), int((h1 - h) / 2.0)
        bbdata = wx.wxMemoryDC()
        bbdata.SelectObject(self.dropTarget)
        bbdata.SetPen(wx.wxTRANSPARENT_PEN)
        bbdata.SetBrush(wx.wxBrush(wx.wxSystemSettings_GetColour(
            wx.wxSYS_COLOUR_MENU), wx.wxSOLID))
        bbdata.DrawRectangle(0, 0, w1, h1)
        bbdata.SetPen(wx.wxBLACK_PEN)
        bbdata.SetBrush(wx.wxTRANSPARENT_BRUSH)
        bbdata.DrawRectangle(x1 - 1, y1 - 1, w + 2, h + 2)
        bbdata.DrawBitmap(bmp, x1, y1, True)
        try:
            self.dropTargetRefresh()
        except:
            pass

    def _dropTargetRead(self, new):
        a, b = os.path.split(new)
        if a and a != os.path.join(basepath, 'targets'):
            if a != os.path.join(basepath, 'targets'):
                b1, b2 = os.path.splitext(b)
                z = 0
                while os.path.isfile(os.path.join(basepath, 'targets', b)):
                    z += 1
                    b = b1 + '(' + str(z) + ')' + b2
                # 2013.02.28 CJJ Changed unknown variable newname to new
                shutil.copyfile(new, os.path.join(basepath, 'targets', b))
            new = b
        name = os.path.join(basepath, 'targets', new)
        garbage, e = os.path.splitext(new.lower())
        if e == '.gif':
            bmp = wx.wxBitmap(name, wx.wxBITMAP_TYPE_GIF)
        elif e == '.bmp':
            bmp = wx.wxBitmap(name, wx.wxBITMAP_TYPE_BMP)
        else:
            assert False
        return bmp

    def dropTargetHovered(self, x=None):
        pass

    def dropTargetUnhovered(self, x=None):
        pass

    def dropTargetDropped(self, x=None):
        pass

    def dropTargetSuccess(self, x=None):
        pass

    def dropTargetError(self, x=None):
        pass

    def switchToBasic(self, x=None):
        self.d.close()
        self.d = BasicDownloadInfo(self.config, self.getCalls())

    def switchToAdvanced(self, x=None):
        self.d.close()
        self.d = AdvancedDownloadInfo(self.config, self.getCalls())


class btWxApp(wx.wxApp):
    def OnInit(self):
        self.APP = T_make()
        return True

if __name__ == '__main__':
    btWxApp().MainLoop()
