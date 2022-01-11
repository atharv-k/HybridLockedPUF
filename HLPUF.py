import netsquid as ns
import pydynaa
from netsquid.nodes import Node, Network
from netsquid.components import Component
from netsquid.nodes.connections import DirectConnection
import random as rd
from netsquid.qubits.qubitapi import *
from netsquid.protocols import NodeProtocol
import numpy as np
from netsquid.components.models import FibreDelayModel, FibreLossModel, DepolarNoiseModel, FixedDelayModel
from netsquid.components import QuantumChannel, ClassicalChannel
from pydynaa.core import SimulationEngine

class ClassicalPUF(Component):

    def __init__(self,N):
        super().__init__(name="Classical_PUF")
        self.no_of_challenges = N
        self.crp = None

    def CRP(self):
        challenge = np.random.RandomState(seed=2).randint(0,2,(self.no_of_challenges,2))
        response = np.random.RandomState(seed=5).randint(0,2,(self.no_of_challenges,4))
        challenge = [tuple(c) for c in challenge]
        response = [tuple(r) for r in response]
        cr_pairs = dict(zip(challenge,response))
        self.crp = cr_pairs

    def eval(self,challenge):
        return np.asarray(self.crp[tuple(challenge)])

class ClientProtocol(NodeProtocol):

    def __init__(self,node):
        super().__init__(node=node)
        self.node.add_subcomponent(ClassicalPUF(N=n),"PUF")

    def run(self):
        puf = self.node.subcomponents["PUF"]
        qin = self.node.ports["client_qport"]
        cout = self.node.ports["client_cport"]
        puf.CRP()
        yield self.await_port_input(cout)
        [challenge] = cout.rx_input().items
        response = puf.eval(challenge)
        response_1 = [bit for index, bit in enumerate(response) if index % 2 == 0]
        response_2 = [bit for index, bit in enumerate(response) if index % 2 != 0]
        response = list(zip(response_1,response_2))
        for element in response:
            qubit, = create_qubits(1,"Q",True)
            if element[0]==0 and element[1]==0:
                assign_qstate(qubit,ns.qubits.ketstates.s0)
            elif element[0]==0 and element[1]==1:
                assign_qstate(qubit,ns.qubits.ketstates.s1)
            elif element[0]==1 and element[1]==0:
                assign_qstate(qubit,ns.qubits.ketstates.h0)
            else:
                assign_qstate(qubit,ns.qubits.ketstates.h1)
            qin.tx_output(qubit)
            yield self.await_timer(1)

class ServerProtocol(NodeProtocol):

    def __init__(self,node):
        super().__init__(node=node)
        self.database = None

    def run(self):
        puf = ClassicalPUF(N=n)
        qin = self.node.ports["server_qport"]
        cout = self.node.ports["server_cport"]
        puf.CRP()
        self.database = puf.crp
        crp = rd.sample(self.database.items(),1)
        [(challenge,response)] = crp
        response_1 = [bit for index, bit in enumerate(response) if index % 2 == 0]
        response_2 = [bit for index, bit in enumerate(response) if index % 2 != 0]
        response = list(zip(response_1,response_2))
        cout.tx_output(challenge)
        received_response = []
        for i in range(len(response)):
            yield self.await_port_input(qin)
            [qubit] = qin.rx_input().items
            if response[i][0]==0:
                m , _ = measure(qubit,ns.Z,discard=True)
                received_response.append((0,m))
                yield self.await_timer(1)
            else:
                m,_ = measure(qubit,ns.X,discard=True)
                received_response.append((1,m))
                yield self.await_timer(1)

        print(f'The response received form the client is matching: {response==received_response}')

        
n = 10000

client = Node("Client", port_names=["client_qport","client_cport"])
server = Node("Server", port_names=["server_qport","server_cport"])

quantum_channel_c2s = QuantumChannel("Quantum_Channel_c2s", length=0.4, transmit_empty_items=True)
quantum_channel_s2c = QuantumChannel("Quantum_Channel_s2c", length=0.4, transmit_empty_items=True)
qconnect = DirectConnection("Connection", channel_AtoB=quantum_channel_c2s, channel_BtoA=quantum_channel_s2c)

classical_channel_c2s = ClassicalChannel("Classical_Channel_c2s", length=0.4, transmit_empty_items=True)
classical_channel_s2c = ClassicalChannel("Classical_Channel_s2c", length=0.4, transmit_empty_items=True)
cconnect = DirectConnection("Connection", channel_AtoB=classical_channel_c2s, channel_BtoA=classical_channel_s2c)

network = Network(name="Network")
network.add_nodes([client, server])
network.add_connection(client, server, connection=qconnect, label="quantum", port_name_node1="client_qport", port_name_node2="server_qport")
network.add_connection(client, server, connection=cconnect, label="classical", port_name_node1="client_cport", port_name_node2="server_cport")

client_protocol = ClientProtocol(client)
server_protocol = ServerProtocol(server)
client_protocol.start()
server_protocol.start()
ns.sim_run()