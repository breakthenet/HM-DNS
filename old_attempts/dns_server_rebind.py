"""
Source: https://github.com/marksteward/rebind
"""
import datetime
import sys
import ConfigParser
import time
import threading
import traceback
import SocketServer
from dnslib import *
import socket
import dns.resolver


class DomainName(str):
    def __getattr__(self, item):
        return DomainName(item + '.' + self)


defaults = {
    'root': 'localhost',
    'ttl': '60',
    'ip': '',
    'port': '5053',
    'serialsuffix': '1',
    'resolver': '8.8.8.8',
}
config = ConfigParser.ConfigParser(defaults)
config.read(['rebind.conf'])

D = DomainName(config.get('rebind', 'root'))
if config.get('rebind', 'ip') == '':
    IP = socket.gethostbyname(D)
else:
    IP = config.get('rebind', 'ip')
TTL = config.getint('rebind', 'ttl')
PORT = config.getint('rebind', 'port')
SERIALSUFFIX = config.get('rebind', 'serialsuffix')
RESOLVER = config.get('rebind', 'resolver')

soa_record = SOA(
    mname=D.ns1,  # primary name server
    rname=D.hostmaster,  # email of the domain administrator
    times=(
        int(datetime.datetime.utcnow().strftime('%Y%m%d') + SERIALSUFFIX), # serial number
        60 * 60 * 1,  # refresh
        60 * 60 * 3,  # retry
        60 * 60 * 24,  # expire
        60 * 60 * 1,  # minimum
    )
)
ns_records = [NS(D.ns1), NS(D.ns2)]
records = {
    D: [A(IP), AAAA((0,) * 16), MX(D.mail), soa_record] + ns_records,
    D.ns1: [A(IP)],  # MX and NS records must never point to a CNAME alias (RFC 2181 section 10.3)
    D.ns2: [A(IP)],
    D.mail: [A(IP)],
    D.hostmaster: [CNAME(D)],
}

clients = {}

def rchop(string, ending):
    if string.endswith(ending):
        return string[:-len(ending)]
    return string

def dns_response(data):
    request = DNSRecord.parse(data)

    print request

    reply = DNSRecord(DNSHeader(id=request.header.id, qr=1, aa=1, ra=1), q=request.q)

    qname = request.q.qname
    qn = rchop(str(qname), '.')

    qtype = request.q.qtype
    qt = QTYPE[qtype]

    if qn in records:
        for rdata in records[qn]:
            rqt = rdata.__class__.__name__
            if qt in ['ANY', rqt]:
                reply.add_answer(RR(rname=qname, rtype=getattr(QTYPE, rqt), rclass=1, ttl=TTL, rdata=rdata))

        if qt in ['ANY']:
            for rdata in ns_records:
                reply.add_ar(RR(rname=D, rtype=QTYPE.NS, rclass=1, ttl=TTL, rdata=rdata))

            reply.add_auth(RR(rname=D, rtype=QTYPE.SOA, rclass=1, ttl=TTL, rdata=soa_record))

    elif not qn.endswith('.' + D):
        pass

    else:
        data = rchop(qn, '.' + D)
        if '.' not in data:
            # Main page - not rebound
            reply.add_answer(RR(rname=qname, rtype=QTYPE.A, rclass=1, ttl=TTL, rdata=A(IP)))
        else:
            target, client = data.rsplit('.', 1)
            if '-' in client:
                op, client = client.split('-', 1)
                op = op.upper()

                if op in ['N', 'R']:
                    clients[client] = op

            if client not in clients:
                clients[client] = 'N'  # normal

            print 'Client %s is currently %s' % (client, clients[client])
            if clients[client] == 'N':
                reply.add_answer(RR(rname=qname, rtype=QTYPE.A, rclass=1, ttl=15, rdata=A(IP)))
            else:
                try:
                    print 'Looking up %s' % target
                    for rdata in dns.resolver.query(target, 'A'):
                        reply.add_answer(RR(rname=qname, rtype=QTYPE.A, rclass=1, ttl=15, rdata=A(rdata.address)))
                except Exception:
                    pass

    print "---- Reply:\n", reply

    return reply.pack()


class BaseRequestHandler(SocketServer.BaseRequestHandler):

    def get_data(self):
        raise NotImplementedError

    def send_data(self, data):
        raise NotImplementedError

    def handle(self):
        now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')
        print "\n\n%s request %s (%s %s):" % (self.__class__.__name__[:3], now, self.client_address[0],
                                               self.client_address[1])
        try:
            data = self.get_data()
            print len(data), data.encode('hex')
            self.send_data(dns_response(data))
        except Exception:
            traceback.print_exc(file=sys.stderr)


class TCPRequestHandler(BaseRequestHandler):

    def get_data(self):
        data = self.request.recv(8192)
        sz = int(data[:2].encode('hex'), 16)
        if sz < len(data) - 2:
            raise Exception("Wrong size of TCP packet")
        elif sz > len(data) - 2:
            raise Exception("Too big TCP packet")
        return data[2:]

    def send_data(self, data):
        sz = ('%04x' % len(data)).decode('hex')
        return self.request.sendall(sz + data)


class UDPRequestHandler(BaseRequestHandler):

    def get_data(self):
        return self.request[0]

    def send_data(self, data):
        return self.request[1].sendto(data, self.client_address)


if __name__ == '__main__':
    print "Starting nameserver..."

    servers = [
        SocketServer.ThreadingUDPServer(('', PORT), UDPRequestHandler),
        SocketServer.ThreadingTCPServer(('', PORT), TCPRequestHandler),
    ]
    for s in servers:
        thread = threading.Thread(target=s.serve_forever)  # that thread will start one more thread for each request
        thread.daemon = True  # exit the server thread when the main thread terminates
        thread.start()
        print "%s server loop running in thread: %s" % (s.RequestHandlerClass.__name__[:3], thread.name)

    try:
        while 1:
            time.sleep(1)
            sys.stderr.flush()
            sys.stdout.flush()

    except KeyboardInterrupt:
        pass
    finally:
        for s in servers:
            s.shutdown()