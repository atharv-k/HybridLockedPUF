import netsquid as ns
from netsquid.nodes import Node, Network
from netsquid.components import Component
from netsquid.nodes.connections import DirectConnection
import random as rd
from netsquid.qubits.qubitapi import *
from netsquid.protocols import NodeProtocol
import numpy as np
from netsquid.components import QuantumChannel, ClassicalChannel

class ClassicalPUF(Component):

    def __init__(self,N):
        super().__init__(name="Classical_PUF")
        self.no_of_challenges = N
        self.crp = None

    def CRP(self):
        challenge = np.random.RandomState(seed=2).randint(0,2,(self.no_of_challenges,8))
        response = np.random.RandomState(seed=5).randint(0,2,(self.no_of_challenges,16))
        challenge = [tuple(c) for c in challenge]
        response = [tuple(r) for r in response]
        cr_pairs = dict(zip(challenge,response))
        self.crp = cr_pairs

    def eval(self,challenge):
        return np.asarray(self.crp[tuple(challenge)])

def response_to_quantum_states(*args):
    state_1 = None
    if args[0][0] == 0 and args[0][1] == 0:
        state_1 = ns.qubits.ketstates.s0
    elif args[0][0] == 0 and args[0][1] == 1:
        state_1 = ns.qubits.ketstates.s1
    elif args[0][0] == 1 and args[0][1] == 0:
        state_1 = ns.qubits.ketstates.h0
    else:
        state_1 = ns.qubits.ketstates.h1
    for i in range(1, len(args)):
        if args[i][0] == 0 and args[i][1] == 0:
            state_1 = np.kron(state_1, ns.qubits.ketstates.s0)
        elif args[i][0] == 0 and args[i][1] == 1:
            state_1 = np.kron(state_1, ns.qubits.ketstates.s1)
        elif args[i][0] == 1 and args[i][1] == 0:
            state_1 = np.kron(state_1, ns.qubits.ketstates.h0)
        else:
            state_1 = np.kron(state_1, ns.qubits.ketstates.h1)

    return state_1

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
        response = list(zip([bit for index, bit in enumerate(response) if index % 2 == 0],[bit for index, bit in enumerate(response) if index % 2 != 0]))
        response_1 = create_qubits(len(response) // 2, "Q", True)
        response_2 = create_qubits(len(response) // 2, "Q", True)
        assign_qstate(response_1, response_to_quantum_states(*response[:len(response) // 2]))
        assign_qstate(response_2, response_to_quantum_states(*response[len(response) // 2:len(response)]))
        yield self.await_port_input(qin)
        r1 = qin.rx_input().items
        if round(fidelity(r1, response_1[0].qstate.qrepr.ket)) == 1:
            qin.tx_output(response_2)
        else:
            print('Authentication failed !!')

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
        response = list(zip([bit for index, bit in enumerate(response) if index % 2 == 0],[bit for index, bit in enumerate(response) if index % 2 != 0]))
        response_1 = create_qubits(len(response) // 2, "Q", True)
        response_2 = create_qubits(len(response) // 2, "Q", True)
        assign_qstate(response_1, response_to_quantum_states(*response[:len(response) // 2]))
        assign_qstate(response_2, response_to_quantum_states(*response[len(response) // 2:len(response)]))
        cout.tx_output(challenge)
        qin.tx_output(response_1)
        yield self.await_port_input(qin)
        r2 = qin.rx_input().items
        if round(fidelity(r2, response_2[0].qstate.qrepr.ket)) == 1:
            print('The client authenticated succesfully!')
        else:
            print('Authentication failed !!')


        
n = 20

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
stats = ns.sim_run()
print(stats)