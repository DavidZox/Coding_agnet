#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <tuple>
#include <sstream>
#include <algorithm>
#include "al_graph.hpp"
#include "am_graph.hpp"

using namespace std;

int main(int argc, char** argv) {
    if (argc < 2) {
        return -1;
    }

    string filename = "";
    string output_path = "";

    if (string(argv[1]) == "file") {
        if (argc < 3) return -1;
        filename = argv[2];
        if (argc >= 4) {
            output_path = argv[3];
        }
    } else {
        // If not "file" mode, the logic depends on how the test calls it.
        // Based on PRD: ./graph file [filename] [output file path]
        // If the user just runs ./graph, we might need to handle it, 
        // but the requirement says "file" mode is the way.
        return -1;
    }

    ifstream infile(filename);
    if (!infile.is_open()) {
        return -1;
    }

    int is_directed;
    if (!(infile >> is_directed)) {
        return -1;
    }

    // Temporary storage to build graphs
    vector<pair<int, int>> edges_raw;
    vector<int> weights;
    int u_val, v_val, w_val;
    int max_v = 0;
    vector<int> vex_list;

    // Read edges and find max vertex index to determine number of vertices
    // Note: The problem doesn't explicitly say how many vertices there are, 
    // but usually it's inferred from the highest index or provided.
    // Looking at the example, vertices are 1-indexed or 0-indexed.
    // Let's collect all edges first.
    while (infile >> u_val >> v_val >> w_val) {
        edges_raw.push_back({u_val, v_val});
        weights.push_back(w_val);
        if (u_val > max_v) max_v = u_val;
        if (v_val > max_v) max_v = v_val;
    }

    // Based on the example output, it seems vertices are 1 to N.
    // Let's assume vertices are 1 to max_v.
    int vex_num = max_v;
    vector<int> vexes;
    for (int i = 1; i <= vex_num; ++i) {
        vexes.push_back(i);
    }

    // Prepare data for setArcs
    // AdjacencyListGraph::setArcs takes vector<tuple<VertexType, VertexType, int>>
    // We must pass the actual vertex labels (tags) because setArcs uses locateVex internally.
    vector<tuple<int, int, int>> arcs_data;
    for (size_t i = 0; i < edges_raw.size(); ++i) {
        arcs_data.push_back(make_tuple(edges_raw[i].first, edges_raw[i].second, weights[i]));
    }

    // Initialize Graphs
    // AdjacencyListGraph(vex_num, arc_num, is_directed)
    // AdjacencyMatrixGraph(vex_num + 1, arc_num, is_directed) per UML_sequence.md
    AdjacencyListGraph<int> alg(vex_num, arcs_data.size(), is_directed == 1);
    AdjacencyMatrixGraph<int> amg(vex_num + 1, arcs_data.size(), is_directed == 1);

    if (!alg.setVexes(vexes) || !alg.setArcs(arcs_data) ||
        !amg.setVexes(vexes) || !amg.setArcs(arcs_data)) {
        return -1;
    }

    // Prepare Output
    ostream* out = &cout;
    ofstream outfile;
    if (!output_path.empty()) {
        outfile.open(output_path);
        if (outfile.is_open()) {
            out = &outfile;
        }
    }

    // Output Adjacency Matrix
    *out << "Adjacency Matrix：" << endl;
    *out << amg << endl;

    // Output Adjacency Table
    *out << "Adjacency Table：" << endl;
    *out << alg << endl;

    // Output DFS (no recursion)
    *out << "Depth-first search (no recursion) " << endl;
    vector<int> dfs_res = alg.dfs_noRes();
    for (size_t i = 0; i < dfs_res.size(); ++i) {
        *out << dfs_res[i] << (i == dfs_res.size() - 1 ? "" : " ");
    }
    *out << endl;

    // Output BFS
    *out << "BFS: " << endl;
    vector<int> bfs_res = alg.bfs();
    for (size_t i = 0; i < bfs_res.size(); ++i) {
        *out << bfs_res[i] << (i == bfs_res.size() - 1 ? "" : " ");
    }
    *out << endl;

    if (outfile.is_open()) {
        outfile.close();
    }

    return 0;
}
