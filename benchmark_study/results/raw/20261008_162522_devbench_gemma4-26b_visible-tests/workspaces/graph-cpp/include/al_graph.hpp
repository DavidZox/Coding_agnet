#ifndef AL_GRAPH_HPP
#define AL_GRAPH_HPP

#include <vector>
#include <tuple>
#include <iostream>
#include <stdexcept>
#include "queue.hpp"
#include "stack.hpp"

template <typename VertexType>
class AdjacencyListGraph {
private:
    struct ArcNode {
        int adjVex;
        int weight;
        ArcNode* next;
        ArcNode(int v, int w, ArcNode* n) : adjVex(v), weight(w), next(n) {}
    };

    struct _vNode {
        VertexType v;
        ArcNode* nextArc;
        _vNode* nextVex;
        _vNode(VertexType val, ArcNode* arc, _vNode* next) : v(val), nextArc(arc), nextVex(next) {}
    };

public:
    AdjacencyListGraph(int vexNum, int arcNum, bool isDirected) 
        : _isDirected(isDirected), _vexNum(vexNum), _arcNum(arcNum), _head(nullptr) {}

    ~AdjacencyListGraph() {
        _vNode* currV = _head;
        while (currV) {
            _vNode* nextV = currV->nextVex;
            ArcNode* currA = currV->nextArc;
            while (currA) {
                ArcNode* nextA = currA->next;
                delete currA;
                currA = nextA;
            }
            delete currV;
            currV = nextV;
        }
    }

    int locateVex(VertexType value) {
        _vNode* curr = _head;
        int index = 0;
        while (curr) {
            if (curr->v == value) return index;
            curr = curr->nextVex;
            index++;
        }
        return -1;
    }

    bool setVexes(std::vector<VertexType> vexes) {
        if (vexes.size() != static_cast<size_t>(_vexNum)) throw std::out_of_range("Size mismatch");
        
        _vNode* currV = _head;
        while (currV) {
            _vNode* nextV = currV->nextVex;
            ArcNode* currA = currV->nextArc;
            while (currA) {
                ArcNode* nextA = currA->next;
                delete currA;
                currA = nextA;
            }
            delete currV;
            currV = nextV;
        }
        _head = nullptr;

        _vNode** last = &_head;
        for (const auto& v : vexes) {
            *last = new _vNode(v, nullptr, nullptr);
            last = &((*last)->nextVex);
        }
        return true;
    }

    bool setArcs(std::vector<std::tuple<VertexType, VertexType, int>> arcs) {
        _vNode* currV = _head;
        while (currV) {
            ArcNode* currA = currV->nextArc;
            while (currA) {
                ArcNode* nextA = currA->next;
                delete currA;
                currA = nextA;
            }
            currV->nextArc = nullptr;
            currV = currV->nextVex;
        }

        for (const auto& arc : arcs) {
            int u = locateVex(std::get<0>(arc));
            int v = locateVex(std::get<1>(arc));
            int w = std::get<2>(arc);
            if (u == -1 || v == -1) return false;

            _vNode* uNode = _getVNode(u);
            // To maintain input order in the linked list, we append to the end.
            // However, for DFS with a stack, we want to push neighbors in reverse order 
            // so the first neighbor is popped first.
            // Let's append to the end of the list to keep the order consistent with the input.
            if (uNode->nextArc == nullptr) {
                uNode->nextArc = new ArcNode(v, w, nullptr);
            } else {
                ArcNode* temp = uNode->nextArc;
                while (temp->next != nullptr) temp = temp->next;
                temp->next = new ArcNode(v, w, nullptr);
            }

            if (!_isDirected) {
                _vNode* vNode = _getVNode(v);
                if (vNode->nextArc == nullptr) {
                    vNode->nextArc = new ArcNode(u, w, nullptr);
                } else {
                    ArcNode* temp = vNode->nextArc;
                    while (temp->next != nullptr) temp = temp->next;
                    temp->next = new ArcNode(u, w, nullptr);
                }
            }
        }
        return true;
    }

    std::vector<VertexType> dfs_noRes() {
        std::vector<VertexType> res;
        if (!_head) return res;

        Stack<int> s;
        std::vector<bool> visited(_vexNum, false);
        
        s.push(0);

        while (!s.empty()) {
            int currIdx = s.pop();
            
            if (visited[currIdx]) continue;
            visited[currIdx] = true;
            res.push_back(_getVexValue(currIdx));

            _vNode* vNode = _getVNode(currIdx);
            ArcNode* aNode = vNode->nextArc;
            
            // To visit neighbors in the order they appear in the adjacency list,
            // we must push them onto the stack in REVERSE order.
            std::vector<int> neighbors;
            while (aNode) {
                neighbors.push_back(aNode->adjVex);
                aNode = aNode->next;
            }
            
            for (int i = (int)neighbors.size() - 1; i >= 0; --i) {
                if (!visited[neighbors[i]]) {
                    s.push(neighbors[i]);
                }
            }
        }
        return res;
    }

    std::vector<VertexType> bfs() {
        _vNode* first = _head;
        if (!first) return {};
        return bfs(first->v);
    }

    std::vector<VertexType> bfs(VertexType start) {
        std::vector<VertexType> res;
        int startIdx = locateVex(start);
        if (startIdx == -1) return res;

        Queue<int> q;
        std::vector<bool> visited(_vexNum, false);

        q.push(startIdx);
        visited[startIdx] = true;

        while (!q.empty()) {
            int currIdx = q.pop();
            res.push_back(_getVexValue(currIdx));

            _vNode* vNode = _getVNode(currIdx);
            ArcNode* aNode = vNode->nextArc;
            
            while (aNode) {
                if (!visited[aNode->adjVex]) {
                    visited[aNode->adjVex] = true;
                    q.push(aNode->adjVex);
                }
                aNode = aNode->next;
            }
        }
        return res;
    }

    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph& graph) {
        _vNode* currV = graph._head;
        int vIdx = 0;
        while (currV) {
            os << vIdx << "\t";
            ArcNode* currA = currV->nextArc;
            while (currA) {
                _vNode* targetV = graph._getVNode(currA->adjVex);
                os << targetV->v << "\t->\t" << targetV->v << "\t" << currA->weight << "\t->\t";
                currA = currA->next;
            }
            os << "^\t";
            currV = currV->nextVex;
            vIdx++;
        }
        return os;
    }

private:
    bool _isDirected;
    int _vexNum;
    int _arcNum;
    _vNode* _head;

    _vNode* _getVNode(int idx) {
        _vNode* curr = _head;
        for (int i = 0; i < idx; ++i) curr = curr->nextVex;
        return curr;
    }

    VertexType _getVexValue(int idx) {
        return _getVNode(idx)->v;
    }
};

#endif
