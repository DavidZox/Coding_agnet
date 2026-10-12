#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <sstream>
#include <tuple>
#include "../include/al_graph.hpp"
#include "../include/am_graph.hpp"

int main(int argc, char** argv) {
    if (argc < 2) {
        return -1;
    }

    std::string mode = argv[1];
    if (mode != "file") {
        return -1;
    }

    if (argc < 3) {
        return -1;
    }

    std::string input_filename = argv[2];
    std::string output_filename = (argc >= 4) ? argv[3] : "";

    std::ifstream infile(input_filename);
    if (!infile.is_open()) {
        return -1;
    }

    int isDirectedInt;
    if (!(infile >> isDirectedInt)) {
        return -1;
    }
    bool isDirected = (isDirectedInt == 1);

    std::vector<std::tuple<int, int, int>> raw_arcs;
    std::vector<int> vertex_set;
    bool found_v[1000] = {false}; // Simple way to collect unique vertices from edges
    int max_v = 0;

    int u, v, w;
    while (infile >> u >> v >> w) {
        raw_arcs.emplace_back(u, v, w);
        if (!found_v[u]) { found_v[u] = true; vertex_set.push_back(u); }
        if (!found_v[v]) { found_v[v] = true; vertex_set.push_back(v); }
        if (u > max_v) max_v = u;
        if (v > max_v) max_v = v;
    }

    // Sort vertices to ensure consistent indexing
    std::sort(vertex_set.begin(), vertex_set.end());

    int vexNum = vertex_set.size();
    int arcNum = raw_arcs.size();

    try {
        // Initialize Graphs
        // Note: UML/Architecture suggests AMG might need vexNum+1 in some contexts, 
        // but based on PRD logic, we use the actual vertex count.
        AdjacencyListGraph<int> alg(vexNum, arcNum, isDirected);
        AdjacencyMatrixGraph<int> amg(vexNum, arcNum, isDirected);

        // Set Vexes
        alg.setVexes(vertex_set);
        amg.setVexes(vertex_set);

        // Set Arcs
        // For ALG, setArcs expects tuple<VertexType, VertexType, int>
        std::vector<std::tuple<int, int, int>> alg_arcs;
        // For AMG, setArcs expects tuple<int, int, int> where ints are indices
        std::vector<std::tuple<int, int, int>> amg_arcs;

        for (const auto& arc : raw_arcs) {
            int src_val = std::get<0>(arc);
            int dst_val = std::get<1>(arc);
            int weight = std::get<2>(arc);

            alg_arcs.emplace_back(src_val, dst_val, weight);

            int src_idx = alg.locateVex(src_val);
            int dst_idx = alg.locateVex(dst_val);
            if (src_idx != -1 && dst_idx != -1) {
                amg_arcs.emplace_back(src_idx, dst_idx, weight);
            }
        }

        alg.setArcs(alg_arcs);
        amg.setArcs(amg_arcs);

        // Prepare Output
        std::ostream* out = &std::cout;
        std::ofstream outfile;
        if (!output_filename.empty()) {
            outfile.open(output_filename);
            if (outfile.is_open()) {
                out = &outfile;
            }
        }

        // 1. Adjacency Matrix
        *out << amg;

        // 2. Adjacency Table
        *out << alg;

        // 3. DFS (no recursion)
        std::vector<int> dfs_res = alg.dfs_noRes();
        *out << "Depth-first search (no recursion) \n";
        for (size_t i = 0; i < dfs_res.size(); ++i) {
            *out << dfs_res[i] << (i == dfs_res.size() - 1 ? "" : " ");
        }
        *out << "\n";

        // 4. BFS
        std::vector<int> bfs_res = alg.bfs();
        *out << "BFS: \n";
        for (size_t i = 0; i < bfs_res.size(); ++i) {
            *out << bfs_res[i] << (i == bfs_res.size() - 1 ? "" : " ");
        }
        *out << "\n";

    } catch (...) {
        return -1;
    }

    return 0;
}
