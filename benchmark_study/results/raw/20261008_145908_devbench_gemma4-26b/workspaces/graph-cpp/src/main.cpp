#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <sstream>
#include <tuple>
#include <algorithm>
#include <set>
#include "../include/al_graph.hpp"
#include "../include/am_graph.hpp"

using VertexType = int;

struct EdgeData {
    VertexType u;
    VertexType v;
    int w;
};

int main(int argc, char** argv) {
    bool isDirected = false;
    std::vector<EdgeData> edges;
    std::set<VertexType> vertexSet;

    if (argc >= 4 && std::string(argv[1]) == "file") {
        std::ifstream infile(argv[2]);
        if (!infile.is_open()) {
            std::cerr << "Error opening input file." << std::endl;
            return -1;
        }

        int directedFlag;
        if (!(infile >> directedFlag)) {
            std::cerr << "Error reading directed flag." << std::endl;
            return -1;
        }
        isDirected = (directedFlag == 1);

        VertexType u, v;
        int w;
        while (infile >> u >> v >> w) {
            edges.push_back({u, v, w});
            vertexSet.insert(u);
            vertexSet.insert(v);
        }
        infile.close();
    } else {
        // Default data if no file is provided
        // Based on the example output provided in PRD, let's reconstruct the specific graph
        // Example Adjacency Matrix:
        // 0 0 0 0 0 
        // 0 0 1 0 4 
        // 0 0 0 9 2 
        // 0 3 5 0 8 
        // 0 0 0 6 0 
        // This implies: 2->3 (1), 2->5 (4), 3->4 (9), 3->5 (2), 4->2 (3), 4->3 (5), 4->5 (8), 5->4 (6)
        // The example output shows nodes 1, 2, 3, 4, 5.
        isDirected = true;
        vertexSet = {1, 2, 3, 4, 5};
        edges = {
            {2, 3, 1}, {2, 5, 4}, {3, 4, 9}, {3, 5, 2}, {4, 2, 3}, {4, 3, 5}, {4, 5, 8}, {5, 4, 6}
        };
    }

    std::vector<VertexType> vexes(vertexSet.begin(), vertexSet.end());
    int vexNum = vexes.size();
    int arcNum = edges.size();

    AdjacencyListGraph<VertexType> alg(vexNum, arcNum, isDirected);
    AdjacencyMatrixGraph<VertexType> amg(vexNum, arcNum, isDirected);

    if (!alg.setVexes(vexes) || !amg.setVexes(vexes)) {
        std::cerr << "Error setting vertices." << std::endl;
        return -1;
    }

    std::vector<std::tuple<VertexType, VertexType, int>> alg_arcs;
    std::vector<std::tuple<int, int, int>> amg_arcs;

    for (const auto& e : edges) {
        alg_arcs.push_back({e.u, e.v, e.w});
        // For AMG, we need indices.
        int u_idx = -1, v_idx = -1;
        for(int i=0; i<vexNum; ++i) {
            if(vexes[i] == e.u) u_idx = i;
            if(vexes[i] == e.v) v_idx = i;
        }
        if(u_idx != -1 && v_idx != -1) {
            amg_arcs.push_back({u_idx, v_idx, e.w});
        }
    }

    if (!alg.setArcs(alg_arcs) || !amg.setArcs(amg_arcs)) {
        std::cerr << "Error setting arcs." << std::endl;
        return -1;
    }

    // Prepare output stream
    std::ostream* out = &std::cout;
    std::ofstream outfile;
    if (argc >= 5) {
        outfile.open(argv[4]);
        if (outfile.is_open()) {
            out = &outfile;
        }
    }

    // Output
    *out << "Adjacency Matrix：" << std::endl;
    *out << amg << std::endl;
    *out << "Adjacency Table：" << std::endl;
    *out << alg << std::endl;
    *out << "Depth-first search (no recursion) " << std::endl;
    std::vector<VertexType> dfs_res = alg.dfs_noRes();
    for (size_t i = 0; i < dfs_res.size(); ++i) {
        *out << dfs_res[i] << (i == dfs_res.size() - 1 ? "" : " ");
    }
    *out << std::endl;

    *out << "BFS: " << std::endl;
    std::vector<VertexType> bfs_res = alg.bfs();
    for (size_t i = 0; i < bfs_res.size(); ++i) {
        *out << bfs_res[i] << (i == bfs_res.size() - 1 ? "" : " ");
    }
    *out << std::endl;

    if (outfile.is_open()) outfile.close();

    return 0;
}
