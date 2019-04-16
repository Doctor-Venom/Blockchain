'''
startstabilizer(stabilizer, delay): Runs the provided 'stabilizer' function in a separate thread, activating it repeatedly after every delay seconds, until the shutdown flag of the Peer object is set.
addhandler(msgtype, handler): Registers a handler function for the given message type with the Peer object. Only one handler function may be provided per message type. Message types do not have to be defined in advance of calling this method.
addrouter(router): Registers a routing function with this peer. Read the section on routing above for details.
addpeer(peerid, host, port): Adds a peer name and IP address/port mapping to the known list of peers.
getpeer(peerid): Returns the (host,port) pair for the given peer name.
removepeer(peerid): Removes the entry corresponding to the supplied peerid from the list of known pairs.
getpeerids(): Return a list of all known peer ids.
numberofpeers():
maxpeersreached():
checklivepeers(): Attempt to connect and send a 'PING' message to all currently known peers to ensure that they are still alive. For any connections that fail, the corresponding entry is removed from the list. This method can be used as a simple 'stabilizer' function for a P2P protocol.
'''
import socket
import struct
import threading
import traceback
from tkinter import *
import time
import ast


def debug(msg):
    """ Prints a message to the screen with the name of the current thread also writes this message to a log file"""
    with open('logfile.txt', 'a+') as f:
        f.write("[{}] {}\n".format(str(threading.currentThread().getName()), msg))
    print("[{}] {}".format(str(threading.currentThread().getName()), msg))


class Peer:
    """Implements the core functionality that might be used by a peer in a P2P network."""

    def __init__(self, maxpeers, serverport, myid=None, serverhost=None):
        """ Initializes a peer with the ability to catalog
        information for up to maxpeers number of peers (maxpeers may be set to 0 to allow unlimited number of peers),
        listening on a given server port , with a given peer name (id) and host address. If not supplied, the
        host address (serverhost) will be determined by attempting to connect to an Internet host like Google."""
        self.debug = True

        self.maxpeers = int(maxpeers)
        self.serverport = int(serverport)
        if serverhost:
            self.serverhost = serverhost
        else:
            self.__initserverhost()

        if myid:
            self.myid = myid
        else:
            self.myid = '{}:{}'.format(self.serverhost, self.serverport)

        self.peerlock = threading.Lock()  # ensure proper access to peers list (maybe better to use threading.RLock (reentrant))
        self.peers = {}  # {peerid : (host, port)} mapping
        self.shutdown = False  # used to stop the main loop

        self.handlers = {}  # {msgtype : handler_function}
        self.router = None

    # --------------------------------------------------------------------------
    def __initserverhost(self):
        """ Attempt to connect to an Internet host in order to determine the local machine's IP address."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # AF_INET: IPv4, SOCK_STREAM: TCP
        s.connect(("www.google.com", 80))
        self.serverhost = s.getsockname()[0]
        s.close()

    # --------------------------------------------------------------------------
    def __debug(self, msg):
        if self.debug:
            debug(msg)

    # --------------------------------------------------------------------------
    def __handlepeer(self, clientsock):
        """
        handlepeer( new socket connection ) returns ()
        Dispatches messages from the socket connection
        """

        self.__debug('New child ' + str(threading.currentThread().getName()))
        self.__debug('Connected ' + str(clientsock.getpeername()))

        host, port = clientsock.getpeername()
        peerconn = PeerConnection(None, host, port, clientsock, debug=True)

        try:
            msgtype, msgdata = peerconn.recvdata()  # every received message contains 2 fields: message type and message data
            if msgtype:
                msgtype = msgtype.upper()
            if msgtype not in self.handlers:
                self.__debug('Not handled: {}: {}'.format(msgtype, msgdata))
            else:
                self.__debug('Handling peer msg: {}: {}'.format(msgtype, msgdata))
                self.handlers[msgtype](peerconn, msgdata)  # start handling the message
        except KeyboardInterrupt:
            raise
        except:
            if self.debug:
                traceback.print_exc()

        self.__debug('Disconnecting ' + str(clientsock.getpeername()))
        peerconn.close()

    # end handlepeer method

    # --------------------------------------------------------------------------
    def __runstabilizer(self, stabilizer, delay):
        while not self.shutdown:
            stabilizer()
            time.sleep(delay)

    # --------------------------------------------------------------------------
    def startstabilizer(self, stabilizer, delay):
        """ Registers and starts a stabilizer function with this peer. The function will be activated every <delay> seconds"""
        t = threading.Thread(target=self.__runstabilizer, args=[stabilizer, delay])
        t.start()

    # --------------------------------------------------------------------------
    def addhandler(self, msgtype, handler):
        """ Registers the handler for the given message type with this peer """
        assert len(msgtype) == 4
        self.handlers[msgtype] = handler

    # --------------------------------------------------------------------------
    def addrouter(self, router):
        """
        Registers a routing function with this peer. The setup of routing is as follows:
        1.This peer maintains a list of other known peers (in self.peers).
        2.The routing function should take the name of a peer (which may not necessarily be present in self.peers)
        and decide which of the known peers a message should be routed to next in order to (hopefully) reach the desired peer.
        3.The router function should return a tuple of three values: (next-peer-id, host, port).
        4.If the message cannot be routed, the next-peer-id should be None.
        """
        self.router = router

    # --------------------------------------------------------------------------
    def addpeer(self, peerid, host, port):
        """ Adds a peer name and host:port mapping to the known list of peers."""
        if peerid not in self.peers and (self.maxpeers == 0 or len(self.peers) < self.maxpeers):
            self.peers[peerid] = (host, int(port))
            return True
        else:
            return False

    # --------------------------------------------------------------------------
    def getpeer(self, peerid):
        """ Returns the (host, port) tuple for the given peer name """
        assert peerid in self.peers  # maybe make this just a return NULL?
        return self.peers[peerid]

    # --------------------------------------------------------------------------
    def removepeer(self, peerid):
        """ Removes peer information from the known list of peers. """
        if peerid in self.peers:
            del self.peers[peerid]

    # --------------------------------------------------------------------------
    def getpeerids(self):
        """ Return a list of all known peer id's. """
        return self.peers.keys()

    # --------------------------------------------------------------------------
    def numberofpeers(self):
        """ Return the number of known peer's. """
        return len(self.peers)

    # --------------------------------------------------------------------------
    def maxpeersreached(self):
        """ Returns whether the maximum limit of names has been added to the list of known peers. Always returns True if maxpeers is set to 0."""
        assert self.maxpeers == 0 or len(self.peers) <= self.maxpeers
        return self.maxpeers > 0 and len(self.peers) == self.maxpeers

    # --------------------------------------------------------------------------
    def makeserversocket(self, port, backlog=5):
        """ Constructs and prepares a server socket listening on the given port."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('', port))
        s.listen(backlog)  # max number of simultaneous connections
        return s

    # --------------------------------------------------------------------------
    def sendtopeer(self, peerid, msgtype, msgdata, waitreply=True):
        """
        sendtopeer( peer id, message type, message data, wait for a reply ) returns [ ( reply type, reply data ), ... ]

        Send a message to the identified peer.
        In order to decide how to send the message, the router handler for this peer will be called.
        If no router function has been registered, it will not work.
        The router function should provide the next immediate peer to whom the message should be forwarded.
        The peer's reply, if it is expected, will be returned.

        Returns None if the message could not be routed.
        """

        if self.router:
            nextpid, host, port = self.router(peerid)
        if not self.router or not nextpid:
            self.__debug('Unable to route {} to {}'.format(msgtype, peerid))
            return None
        # host,port = self.peers[nextpid]
        return self.connectandsend(host, port, msgtype, msgdata, pid=nextpid, waitreply=waitreply)

    # --------------------------------------------------------------------------
    def connectandsend(self, host, port, msgtype, msgdata, pid=None, waitreply=True):
        """
        connectandsend( host, port, message type, message data, peer id, wait for a reply ) returns [ ( reply type, reply data ), ... ]

        Connects and sends a message to the specified host:port.
        The host's reply, if expected, will be returned as a list of tuples.
        """
        msgreply = []
        try:
            peerconn = PeerConnection(pid, host, port, debug=self.debug)
            peerconn.senddata(msgtype, msgdata)
            self.__debug('Sent {}: {}'.format(pid, msgtype))

            if waitreply:
                onereply = peerconn.recvdata()
                while (onereply != (None, None)):
                    msgreply.append(onereply)
                    self.__debug('Got reply {}: {}'.format(pid, str(msgreply)))
                    onereply = peerconn.recvdata()
            peerconn.close()
        except KeyboardInterrupt:
            raise
        except:
            if self.debug:
                traceback.print_exc()

        return msgreply

        # end connectsend method

    # --------------------------------------------------------------------------
    def checklivepeers(self):
        """ Attempts to ping all currently known peers in order to ensure that they are still active.
        Removes any from the peer list that do not reply.
        This function can be used as a simple stabilizer.
        """
        todelete = []
        for pid in self.peers:
            isconnected = False
            try:
                self.__debug('Check live {}'.format(pid))
                host, port = self.peers[pid]
                peerconn = PeerConnection(pid, host, port, debug=self.debug)
                peerconn.senddata('PING', 'keepaliveMSG')
                isconnected = True
            except:
                traceback.print_exc()
                todelete.append(pid)
            if isconnected:
                peerconn.close()

        self.peerlock.acquire()
        try:
            for pid in todelete:
                if pid in self.peers:
                    del self.peers[pid]
        finally:
            self.peerlock.release()

        # end checklivepeers method

    # --------------------------------------------------------------------------
    def mainloop(self):
        s = self.makeserversocket(self.serverport)
        s.settimeout(2)
        self.__debug('Server started: {} ({}:{})'.format(self.myid, self.serverhost, self.serverport))

        while not self.shutdown:
            try:
                self.__debug('Listening for connections...')
                clientsock, clientaddr = s.accept()
                clientsock.settimeout(None)

                t = threading.Thread(target=self.__handlepeer, args=[clientsock])
                t.start()
            except KeyboardInterrupt:
                print('KeyboardInterrupt: stopping mainloop')
                self.shutdown = True
                continue
            except:
                #if self.debug:
                    #traceback.print_exc()
                continue

        # end while loop
        self.__debug('Main loop exiting')
        s.close()
        # end mainloop method


# end Peer class

# **********************************************************************************************************************

class PeerConnection:

    # --------------------------------------------------------------------------
    def __init__(self, peerid, host, port, sock=None, debug=True):
        # any exceptions thrown upwards

        self.id = peerid
        self.debug = debug

        if not sock:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s.connect((host, int(port)))
        else:
            self.s = sock

        self.sd = self.s.makefile('rwb', None)

    # --------------------------------------------------------------------------
    def __makemsg(self, msgtype, msgdata):
        msglen = len(msgdata)
        msg = struct.pack("!4sL{}s".format(msglen), msgtype.encode('utf-8'), msglen, msgdata.encode('utf-8'))
        return msg

    # --------------------------------------------------------------------------
    def __debug(self, msg):
        if self.debug:
            debug(msg)

    # --------------------------------------------------------------------------
    def senddata(self, msgtype, msgdata):
        """
        senddata( message type, message data ) returns boolean status

        Send a message through a peer connection. Returns True on success
        or False if there was an error.
        """

        try:
            msg = self.__makemsg(msgtype, msgdata)
            self.sd.write(msg)
            self.sd.flush()
        except KeyboardInterrupt:
            raise
        except:
            if self.debug:
                traceback.print_exc()
            return False
        return True

    # --------------------------------------------------------------------------
    def recvdata(self):
        """
        recvdata() returns (msgtype, msgdata)

        Receive a message from a peer connection. Returns (None, None) if there was any error.
        """

        try:
            recvmsg = self.sd.read()
            msgtype = recvmsg[0:4].decode('utf-8')
            if not msgtype:
                return (None, None)
            msglen = int(struct.unpack("!L", recvmsg[4:8])[0])
            msg = recvmsg[8:].decode('utf-8')

            if len(msg) != msglen:
                return (None, None)

        except KeyboardInterrupt:
            raise
        except:
            if self.debug:
                traceback.print_exc()
            return (None, None)

        return (msgtype, msg)

    # end recvdata method

    # --------------------------------------------------------------------------
    def close(self):
        """
        Close the peer connection.
        The send and recv methods will not work after this call.
        """

        self.s.close()
        self.s = None
        self.sd = None

    # --------------------------------------------------------------------------
    def __str__(self):
        return "|{}|".format(id)


# end PeerConnection class
# ***********************************************************************************************************************

PEERNAME = "NAME"  # request a peer's id
LISTPEERS = "LIST"  # request a list of peers
INSERTPEER = "JOIN"  # request to insert the sender into the peerlist of the receiver
UPDATE = "UPDT"  # send an update message with new transaction to other peers so they can update their DBs
FILEGET = "FGET"  # request a copy of the DB
FILERES = "FRES"  # indicates a response to FGET message with the DB as msgdata
PEERQUIT = "QUIT"  # request the receiver to remove the sender from its peerlist
REPLY = "REPL"  # indicates an acknowledgement message, used for debugging
ERROR = "ERRO"  # indicates that an error happened wihle handling a message, used for debugging


''' 
Assumption in this program: peer id's in this application are just "host:port" strings, must be changed later to a 
public key of asymmetric cryptography
'''
# ==============================================================================

class DLPeer(Peer):  # inherits from class Peer
    """ Implements a Distributed Ledger peer-to-peer entity based on the generic BerryTella P2P framework."""

    # --------------------------------------------------------------------------
    def __init__(self, maxpeers, serverport):
        """
        Initializes the peer to support connections up to maxpeers number
        of peers, with its server listening on the specified port. Also sets
        the dictionary of local files to empty and adds handlers to the
        Peer framework.
        """
        Peer.__init__(self, maxpeers, serverport)  # calls the constructor of class Peer
        self.DB = {}  # peerid + timestapm: transaction
        # firstpeer = self.getpeerids()
        #must find a way to initialize self.DB by sending a FGET message to the first added peer to get a copy of existing DB upon starting the node

        self.addrouter(self.__router)

        handlers = {
            LISTPEERS: self.__handle_listpeers,
            INSERTPEER: self.__handle_insertpeer,
            PEERNAME: self.__handle_peername,
            UPDATE: self.__handle_update,
            FILEGET: self.__handle_DBget,
            FILERES: self.__handle_DBgetresponse,
            PEERQUIT: self.__handle_quit
        }
        for msgT in handlers:
            self.addhandler(msgT, handlers[msgT])

    # end DLPeer constructor

    # --------------------------------------------------------------------------
    def __debug(self, msg):
        if self.debug:
            debug(msg)

    # --------------------------------------------------------------------------
    def __router(self, peerid):
        if peerid not in self.getpeerids():
            return (None, None, None)
        else:
            rt = [peerid]
            rt.extend(self.peers[peerid])
            return rt

    # --------------------------------------------------------------------------
    def __handle_insertpeer(self, peerconn, data):
        # --------------------------------------------------------------------------
        """
        Handles the INSERTPEER (join) message type.
        The message data should be a string of the form, "peerid  host  port", where peer-id is the canonical name of 
        the peer that desires to be added to this peer's list of peers, host and port are the necessary data to connect
        to the peer.
        """
        self.peerlock.acquire()
        try:
            try:
                host, port = data.split()

                if self.maxpeersreached():
                    self.__debug('maxpeers {} reached: connection terminating'.format(self.maxpeers))
                    peerconn.senddata(ERROR, 'Join: max peers reached.')
                    return

                peerid = '{}:{}'.format(host, port)
                if peerid not in self.getpeerids() and peerid != self.myid:
                    self.addpeer(peerid, host, port)
                    self.__debug('added peer: {}'.format(peerid))
                    peerconn.senddata(REPLY, 'Join: peer added: {}'.format(peerid))
                else:
                    peerconn.senddata(ERROR, 'Join: peer already inserted {}'.format(peerid))
            except:
                self.__debug('invalid insert {}: {}'.format(str(peerconn), data))
                peerconn.senddata(ERROR, 'Join: incorrect arguments')
        finally:
            self.peerlock.release()

    # end handle_insertpeer method

    # --------------------------------------------------------------------------
    def __handle_listpeers(self, peerconn, data):
        """ Handles the LISTPEERS message type. Message data is not used. """
        self.peerlock.acquire()
        try:
            self.__debug('Listing peers {}'.format(self.numberofpeers()))
            peerconn.senddata(REPLY, '{}'.format(self.numberofpeers()))
            for pid in self.getpeerids():
                host, port = self.getpeer(pid)
                peerconn.senddata(REPLY, '{}  {} {}'.format(pid, host, port))
        finally:
            self.peerlock.release()

    # --------------------------------------------------------------------------
    def __handle_peername(self, peerconn, data):
        """ Handles the NAME message type. Message data is not used. """
        peerconn.senddata(REPLY, self.myid)

    # --------------------------------------------------------------------------
    def __handle_update(self, peerconn, data):
        """
        UPDT message is sent with additional data (sender-pid*timestamp*transaction) to request a responding node to add the
        transaction to its database.
        if transaction ID (peerid+timestamp) is already in the database, discard the message and dont forward it to other nodes.
        otherwise add it to the database self.DB and forward it to all nodes in the peer dictionary
        """
        peerid, timestamp, transaction = data.split('*')
        if (str(peerid)+str(timestamp)) in self.DB:
            self.__debug('Transaction [{}] is already in the DB'.format(transaction))
        else:
            self.DB[str(peerid)+str(timestamp)] = '[{}]'.format(transaction)
            for i in self.peers.keys():
                host, port = i.split(':')
                self.connectandsend(host, int(port), UPDATE, data, pid=i)
                self.__debug("Transaction [{}:{}]-{} forwarded to peer[{}] for updating.".format(peerid, timestamp, transaction, i))

    # --------------------------------------------------------------------------
    def __handle_DBget(self, peerconn, data):
        """
        FGET message is sent with additional data (sender pid, name of DB file) to request a copy of the Data base when first connected to the network.
        if DB file is not found on the responding node, the message is forwarded to all nodes in the peer dictionary of the responding node.
        otherwise a copy of the file is sent back as a payload of REPL message.
        
        !!!all features are not implemented yet!!!
        """
        
        host, port = data.split(":")
        self.connectandsend(host, port, FILERES, str(self.DB), pid='{}:{}'.format(host, port), waitreply=False)

    # --------------------------------------------------------------------------
    def __handle_DBgetresponse(self, peerconn, data):
        """
        handles FRES message type.
        :param peerconn: not used
        :param data: contains a DB that comes as a response from another node after sending FGET message to it
        :return: nothing
        """
        DB = ast.literal_eval(data)
        for i in DB:  # add only these transactions that are not present in self.DB
            if i not in self.DB:
                self.DB[i] = DB[i]

    # --------------------------------------------------------------------------
    def __handle_quit(self, peerconn, data):
        """
        Handles the QUIT message type.
        The message data should be in the format of a string, "peer-id", where peer-id is the canonical
        name of the peer that wishes to be unregistered from this peer's directory.
        """
        self.peerlock.acquire()
        try:
            peerid = data.lstrip().rstrip()
            if peerid in self.getpeerids():
                msg = 'Quit: peer removed: {}'.format(peerid)
                self.__debug(msg)
                peerconn.senddata(REPLY, msg)
                self.removepeer(peerid)
            else:
                msg = 'Quit: peer not found: {}'.format(peerid)
                self.__debug(msg)
                peerconn.senddata(ERROR, msg)
        finally:
            self.peerlock.release()

    # !!!may be a good idea to hold the lock before going into this function!!!
    # --------------------------------------------------------------------------
    def buildpeers(self, host, port, hops=1):
        """
        buildpeers(host, port, hops)

        Attempt to build the local peer list up to the limit stored by self.maxpeers, using a simple depth-first search 
        given an initial host and port as starting point.
        The depth of the search is limited by the hops parameter. as TTL
        
        !!!this method is still unstable and buggy!!!
        """
        if self.maxpeersreached() or not hops:
            return

        peerid = None

        self.__debug("Building peers from ({}:{})".format(host, port))

        try:
            _, peerid = self.connectandsend(host, port, PEERNAME, '')[0]

            self.__debug("contacted " + peerid)
            resp = self.connectandsend(host, port, INSERTPEER, '{} {} {}'.format(self.myid, self.serverhost, self.serverport))[0]
            self.__debug(str(resp))
            if (resp[0] != REPLY) or (peerid in self.getpeerids()):
                return

            self.addpeer(peerid, host, port)

            # do recursive depth first search to add more peers
            resp = self.connectandsend(host, port, LISTPEERS, '', pid=peerid)
            if len(resp) > 1:
                resp.reverse()
                resp.pop()  # get rid of header count reply
                while len(resp):
                    nextpid, host, port = resp.pop()[1].split()
                    if nextpid != self.myid:
                        self.buildpeers(host, port, hops - 1)
        except:
            if self.debug:
                traceback.print_exc()
            self.removepeer(peerid)

    # --------------------------------------------------------------------------
    def addTransaction(self, transaction):
        """ adds a transaction to the DB and broadcasts the UPDATE message """
        timestamp = int(time.time())
        self.DB[str(self.myid) + str(timestamp)] = '[{}]'.format(transaction)
        self.__debug("Transaction [{}:{}]-{} added successfully".format(self.myid, timestamp, transaction))
        for i in self.peers.keys():
            try:
                host, port = self.peers[i][0], self.peers[i][1]
                self.connectandsend(host, int(port), UPDATE, '{}*{}*{}'.format(self.myid, timestamp, transaction), pid='{}:{}'.format(host, port), waitreply=False)
                self.__debug("Transaction [{}:{}]-{} sent to peer[{}] for updating.".format(self.myid, timestamp, transaction, i))
            except:
                self.__debug("Could not send transaction [{}:{}]-{} to peer[{}] for updating.".format(self.myid, timestamp, transaction, i))

#end DLpeer class
# **********************************************************************************************************************

class DL_GUI(Frame):
    """
    Module implementing simple GUI for a simple p2p network.

    Refresh: Synchronizes the contents of the GUI list components with the internal peer and file lists of the node.
             This operation happens automatically every few seconds.

    Remove: Removes the selected node id from the peer list.

    Rebuild: Takes a "host:port" string from the accompanying text box and uses it to invoke the buildpeers method of 
             the DLPeer class, attempting to populate the list of known peers.

    update DB: Sends a FGET message with its peerID and the requested DB file name to all peers in the list. !!!not fully implemented yet!!!
            Responses to the FGET message will not arrive immediately.
            FRES messages received in the background will be handled by the mainloop of the peer.
            If a new entry is in added tot the transactions list, it will be reflected in the next refresh of the GUI

    Add transaction: adds a transaction to self.DB and broadcast and update message to all known peers in self.peers of class Peer.
         Transactions and the whole self.DB is stored on the RAM, must modify the program to make it store it on the secondary storage.
    """
    def __init__(self, firstpeer, hops=2, maxpeers=5, serverport=6917, master=None):
        Frame.__init__(self, master)
        self.grid()
        self.createWidgets()
        self.master.title("Distributed Ledger GUI {}".format(serverport))
        self.btpeer = DLPeer(maxpeers, serverport)

        self.bind("<Destroy>", self.__onDestroy)

        host, port = firstpeer.split(':')
        self.btpeer.buildpeers(host, int(port), hops=hops)
        self.updatePeerList()

        t = threading.Thread(target=self.btpeer.mainloop, args=[])
        t.start()

        self.btpeer.startstabilizer(self.btpeer.checklivepeers, 10)
        # self.btpeer.startstabilizer( self.onRefresh, 3 )
        self.after(3000, self.onTimer)

    def onTimer(self):
        self.onRefresh()
        self.after(3000, self.onTimer)
        # self.after_idle( self.onTimer )

    def __onDestroy(self, event):
        self.btpeer.shutdown = True

    def updatePeerList(self):
        if self.peerList.size() > 0:
            self.peerList.delete(0, self.peerList.size() - 1)
        for p in self.btpeer.getpeerids():
            self.peerList.insert(END, p)

    def updateDB(self):
        if self.Translist.size() > 0:
            self.Translist.delete(0, self.Translist.size() - 1)
        for f in self.btpeer.DB:
            p = self.btpeer.DB[f]
            if not p:
                p = '(local)'
            self.Translist.insert(END, "{}:{}".format(f, p))

    def createWidgets(self):
        """
        Set up the frame widgets
        """
        DBFrame = Frame(self)
        peerFrame = Frame(self)
        rebuildFrame = Frame(self)
        insertpeerFrame = Frame(self)
        addTransFrame = Frame(self)
        quit_refresh_Frame = Frame(self)

        DBFrame.grid(row=0, column=0, sticky=N + S)
        peerFrame.grid(row=0, column=1, sticky=N + S)
        quit_refresh_Frame.grid(row=1, column=1)
        addTransFrame.grid(row=2)
        insertpeerFrame.grid(row=2, column=1)
        rebuildFrame.grid(row=3, column=1)

        Label(DBFrame, text='DB contents').grid()
        Label(peerFrame, text='Peer List').grid()

        TransactionsFrame = Frame(DBFrame, height=10, width=50)
        TransactionsFrame.grid(row=1, column=0)
        DBScrolly = Scrollbar(TransactionsFrame, orient=VERTICAL)
        DBScrollx = Scrollbar(TransactionsFrame, orient=HORIZONTAL)
        DBScrolly.grid(row=0, column=1, sticky=N + S)
        DBScrollx.grid(row=1, column=0, sticky=W + E)


        self.Translist = Listbox(TransactionsFrame, height=10, yscrollcommand=DBScrolly.set)
        self.Translist = Listbox(TransactionsFrame, width=50, xscrollcommand=DBScrollx.set)
        self.Translist.grid(row=0, column=0, sticky=N + S)
        DBScrolly["command"] = self.Translist.yview
        DBScrollx["command"] = self.Translist.xview

        self.updateButton = Button(DBFrame, text='Update DB', command=self.onUpdate)
        self.updateButton.grid()

        self.addTransEntry = Entry(addTransFrame, width=40)
        self.addtransButton = Button(addTransFrame, text='Add Transaction', command=self.onAdd)
        self.addTransEntry.grid(row=0, column=0)
        self.addtransButton.grid(row=0, column=1)


        self.addpeerEntry = Entry(insertpeerFrame, width=25)
        self.addpeerButton = Button(insertpeerFrame, text='Add Peer', command=self.onAddpeer)
        self.addpeerEntry.grid(row=0, column=0)
        self.addpeerButton.grid(row=0, column=1)

        peerListFrame = Frame(peerFrame)
        peerListFrame.grid(row=1, column=0)
        peerScroll = Scrollbar(peerListFrame, orient=VERTICAL)
        peerScroll.grid(row=0, column=1, sticky=N + S)

        self.peerList = Listbox(peerListFrame, height=10, yscrollcommand=peerScroll.set)
        # self.peerList.insert( END, '1', '2', '3', '4', '5', '6' )
        self.peerList.grid(row=0, column=0, sticky=N + S)
        peerScroll["command"] = self.peerList.yview

        self.removeButton = Button(quit_refresh_Frame, text='send QUIT', command=self.onRemove)
        self.refreshButton = Button(quit_refresh_Frame, text='Refresh GUI', command=self.onRefresh)

        self.rebuildEntry = Entry(rebuildFrame, width=25)
        self.rebuildButton = Button(rebuildFrame, text='Build peer dict', command=self.onRebuild)
        self.removeButton.grid(row=0, column=0)
        self.refreshButton.grid(row=0, column=1)
        self.rebuildEntry.grid(row=0, column=0)
        self.rebuildButton.grid(row=0, column=1)

        # print "Done"

    def onAdd(self):
        Transaction = self.addTransEntry.get()
        if Transaction.lstrip().rstrip():
            T = Transaction.lstrip().rstrip()
            th = threading.Thread(target=self.btpeer.addTransaction, args=[T])
            th.start()
        self.addTransEntry.delete(0, len(Transaction))
        self.updateDB()

    def onAddpeer(self):
        key = self.addpeerEntry.get()
        self.addpeerEntry.delete(0, len(key))
        peerid = key.lstrip().rstrip()
        host, port = peerid.split(':')
        self.btpeer.peers[str(peerid)] = (host, port)
        self.updatePeerList()

    def onUpdate(self):
        try:
            host, port = list(self.btpeer.getpeerids())[0].split(':')
            self.btpeer.connectandsend(host, port, FILEGET, self.btpeer.myid, pid='{}:{}'.format(host, port), waitreply=False)
        except:
            if len(self.btpeer.peers) == 0:
                debug('There are no peers in the peer dict to request a copy of DB.')
            else:
                debug('Can not connect to the peer to request a copy of DB.')

    def onRemove(self):
        sels = self.peerList.curselection()
        if len(sels) == 1:
            peerid = self.peerList.get(sels[0])
            self.btpeer.sendtopeer(peerid, PEERQUIT, self.btpeer.myid)
            self.btpeer.removepeer(peerid)

    def onRefresh(self):
        self.updatePeerList()
        self.updateDB()

    def onRebuild(self):
        if not self.btpeer.maxpeersreached():
            peerid = self.rebuildEntry.get()
            self.rebuildEntry.delete(0, len(peerid))
            peerid = peerid.lstrip().rstrip()
            try:
                host, port = peerid.split(':')
                print ("doing rebuild", peerid, host, port)
                self.btpeer.buildpeers(host, port, hops=3)
            except:
                if self.btpeer.debug:
                    traceback.print_exc()



#***********************************************************************************************************************

def main():
    if len(sys.argv) < 4:
        print("Syntax: [{}] [server-port] [max-peers] [peer-ip:port]".format(sys.argv[0]))
        sys.exit(-1)

    serverport = int(sys.argv[1])
    maxpeers = sys.argv[2]
    peerid = sys.argv[3]
    app = DL_GUI(firstpeer=peerid, maxpeers=maxpeers, serverport=serverport)
    app.mainloop()


if __name__ == '__main__':
    main()