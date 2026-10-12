#ifndef AL_GRAPH_HPP
#define AL_GRAPH_HPP

#include <vector>
#include <tuple>
#include <iostream>
#include <algorithm>
#include <map>
#include <iterator> // Required for std::find
#include "queue.hpp"
#include "stack.hpp"

template <typename VertexType>
class AdjacencyListGraph {
private:
    bool _isDirected;
    int _vexNum;
    int _arcNum;

    struct ArcNode {
        int adjVex;
        int weight;
        ArcNode* next;

        ArcNode(int v, int w) : adjVex(v), weight(w), next(nullptr) {}
    };

    struct _vNode {
        VertexType v;
        ArcNode* next;

        _vNode(const VertexType& val) : v(val), next(nullptr) {}
    };

    std::vector<ArcNode*> _head;
    std::vector<_vNode*> _vexList;

public:
    AdjacencyListGraph(bool isDirected, int vexNum, int arcNum)
        : _isDirected(isDirected), _vexNum(vexNum), _arcNum(arcNum) {
        _head.resize(_vexNum, nullptr);
        _vexList.resize(_vexNum); // FIX: Use resize instead of reserve to ensure correct size for iteration/destruction
    }

    // Destructor to clean up memory
    ~AdjacencyListGraph() {
        for (int i = 0; i < _vexNum; ++i) {
            ArcNode* current = _head[i];
            while (current != nullptr) {
                ArcNode* next = current->next;
                delete current;
                current = next;
            }
            delete _vexList[i]; // FIX: Accessing element at index i, which is now guaranteed to exist
        }
    }

    // Set vertices (Renamed from setVexes to setVexer to match UML)
    bool setVexer(const std::vector<VertexType>& vexes) {
        if (vexes.size() != static_cast<size_t>(_vexNum)) {
            return false;
        }
        // Clean up existing nodes before replacement
        for(int i = 0; i < _vexNum; ++i) {
            delete _vexList[i];
        }
        _vexList.clear();
        for (const auto& v : vexes) {
            _vNode* newNode = new _vNode(v);
            _vexList.push_back(newNode);
        }
        return true;
    }

    // Set arcs (Signature matches UML: vector<tuple<VertexType, VertexType, int>>)
    bool setArcs(const std::vector<std::tuple<VertexType, VertexType, int>>& arcs) {
        if (arcs.size() != static_cast<size_t>(_arcNum)) {
            return false;
        }

        // Clear existing arcs
        for (int i = 0; i < _vexNum; ++i) {
            ArcNode* current = _head[i];
            while (current != nullptr) {
                ArcNode* next = current->next;
                delete current;
                current = next;
            }
            _head[i] = nullptr;
        }

        // Add new arcs
        for (const auto& arc : arcs) {
            VertexType u_val = std::get<0>(arc);
            VertexType v_val = std::get<1>(arc);
            int weight = std::get<2>(arc);

            int u_idx = locateVex(u_val);
            int v_idx = locateVex(v_val);

            if (u_idx == -1 || v_idx == -1) {
                // Should not happen if setVexer was successful and arcs match vertex set
                return false;
            }

            // Create new arc node
            ArcNode* newArc = new ArcNode(v_idx, weight);

            // Insert at the beginning of the adjacency list for u_idx
            newArc->next = _head[u_idx];
            _head[u_idx] = newArc;

            // If undirected, add the reverse arc
            if (!_isDirected) {
                ArcNode* reverseArc = new ArcNode(u_idx, weight);
                reverseArc->next = _head[v_idx];
                _head[v_idx] = reverseArc;
            }
        }
        return true;
    }

    // Find vertex index
    int locateVex(VertexType value) {
        for (int i = 0; i < _vexNum; ++i) {
            if (_vexList[i]->v == value) {
                return i;
            }
        }
        return -1;
    }

    // DFS traversal (non-recursive)
    std::vector<VertexType> dfs_noRes() {
        std::vector<VertexType> result;
        if (_vexNum == 0) return result;

        std::vector<bool> visited(_vexNum, false);
        Stack<int> s; // Using custom Stack

        // Start from the first vertex (index 0)
        s.push(0);
        visited[0] = true;
        result.push_back(_vexList[0]->v);

        while (!s.empty()) {
            int u_idx = s.top();
            s.pop();

            // Iterate through neighbors of u_idx
            std::vector<int> neighbors;
            ArcNode* temp = _head[u_idx];
            while (temp != nullptr) {
                int v_idx = temp->adjVex;
                neighbors.push_back(v_idx);
                temp = temp->next;
            }
            
            // Sort neighbors to ensure deterministic traversal order (e.g., smallest index first)
            std::sort(neighbors.begin(), neighbors.end());
            
            // Push neighbors onto the stack in reverse order so that smaller index is processed first (LIFO)
            for (auto it = neighbors.rbegin(); it != neighbors.rend(); ++it) {
                int v_idx = *it;
                if (!visited[v_idx]) {
                    visited[v_idx] = true;
                    result.push_back(_vexList[v_idx]->v);
                    s.push(v_idx);
                }
            }
        }
        return result;
    }

    // BFS traversal
    std::vector<VertexType> bfs() {
        std::vector<VertexType> result;
        if (_vexNum == 0) return result;

        std::vector<bool> visited(_vexNum, false);
        Queue<int> q; // Using custom Queue
        
        // Start from the first vertex (index 0)
        q.push(0);
        visited[0] = true;
        result.push_back(_vexList[0]->v);

        while (!q.empty()) {
            int u_idx = q.front();
            q.pop();

            // Iterate through neighbors of u_idx
            std::vector<int> neighbors;
            ArcNode* temp = _head[u_idx];
            while (temp != nullptr) {
                int v_idx = temp->adjVex;
                neighbors.push_back(v_idx);
                temp = temp->next;
            }
            
            // Sort neighbors for deterministic traversal order
            std::sort(neighbors.begin(), neighbors.end());

            for (int v_idx : neighbors) {
                if (!visited[v_idx]) {
                    visited[v_idx] = true;
                    result.push_back(_vexList[v_idx]->v);
                    q.push(v_idx);
                }
            }
        }
        return result;
    }

    // Friend operator<< for printing (as required by UML)
    friend std::ostream& operator<<(std::ostream& os, const AdjacencyListGraph& graph) {
        os << "Adjacency List (Not fully implemented for printing in this scope)";
        return os;
    }
};

#endif // AL_GRAPH_HPP
