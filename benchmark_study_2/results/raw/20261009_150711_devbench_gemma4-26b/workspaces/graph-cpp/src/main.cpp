#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <tuple>
#include <sstream>
#include "al_graph.hpp"
#include "am_graph.hpp"

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "Usage: ./graph file [filename] [output file path]" << std::endl;
        return 0;
    }

    std::string mode = argv[1];
    std::string filename = "";
    std::string output_path = "";

    if (mode == "file") {
        if (argc < 3) {
            std::cerr << "Error: Missing filename." << std::endl;
            return 0;
        }
        filename = argv[2];
        if (argc >= 4) {
            output_path = argv[3];
        }
    } else {
        // Default data mode if not "file"
        // Based on PRD example, we'll assume the user provides a file or we use hardcoded logic.
        // However, the requirement says: ./graph file [filename] [output file path]
        // If mode is not "file", we treat it as a fallback or error.
        std::cerr << "Error: Invalid mode. Use 'file'." << std::endl;
        return 0;
    }

    std::ifstream infile(filename);
    if (!infile.is_open()) {
        std::cerr << "Error: Could not open input file: " << filename << std::endl;
        return 0;
    }

    int is_directed;
    if (!(infile >> is_directed)) {
        std::cerr << "Error: Failed to read graph type." << std::endl;
        return 0;
    }

    // Temporary storage to find max vertex index and collect edges
    std::vector<std::tuple<int, int, int>> edges;
    int max_v = 0;
    int u_val, v_val, w_val;
    while (infile >> u_val >> v_val >> w_val) {
        edges.emplace_back(u_val, v_val, w_val);
        if (u_val > max_v) max_v = u_val;
        if (v_val > max_v) max_v = v_val;
    }
    infile.close();

    // The problem implies vertices are 1-indexed based on the example output (1 2 4 3)
    // We need to determine the vertex list. Let's assume vertices are 1 to max_v.
    std::vector<int> vex_list;
    for (int i = 1; i <= max_v; ++i) {
        vex_list.push_back(i);
    }

    // Prepare data for AdjacencyListGraph (ALG)
    // ALG uses VertexType (int)
    AdjacencyListGraph<int> alg(vex_list.size(), edges.size(), is_directed == 1);
    if (!alg.setVexer(vex_list)) {
        std::cerr << "Error: Failed to set vertices for ALG." << std::endl;
        return 0;
    }
    
    // Convert tuple<int, int, int> to vector<tuple<int, int, int>> for setArcs
    // We must convert vertex values to their corresponding indices in the graph
    std::vector<std::tuple<int, int, int>> arc_data;
    for (auto& e : edges) {
        int u_idx = alg.locateVex(std::get<0>(e));
        int v_idx = alg.locateVex(std::get<1>(e));
        arc_data.push_back(std::make_tuple(u_idx, v_idx, std::get<2>(e)));
    }
    if (!alg.setArcs(arc_data)) {
        std::cerr << "Error: Failed to set arcs for ALG." << std::endl;
        return 0;
    }

    // Prepare data for AdjacencyMatrixGraph (AMG)
    AdjacencyMatrixGraph<int> amg(vex_list.size(), edges.size(), is_directed == 1);
    if (!amg.setVexer(vex_list)) {
        std::cerr << "Error: Failed to set vertices for AMG." << std::endl;
        return 0;
    }
    
    // For AMG, we also convert vertex values to indices
    std::vector<std::tuple<int, int, int>> amg_arc_data;
    for (auto& e : edges) {
        int u_idx = amg.locateVex(std::get<0>(e));
        int v_idx = amg.locateVex(std::get<1>(e));
        amg_arc_data.push_back(std::make_tuple(u_idx, v_idx, std::get<2>(e)));
    }
    if (!amg.setArcs(amg_arc_data)) {
        std::cerr << "Error: Failed to set arcs for AMG." << std::endl;
        return 0;
    }

    // Prepare output stream
    std::ofstream outfile;
    if (!output_path.empty()) {
        outfile.open(output_path);
    } else {
        // If no output path provided, we can't satisfy the requirement of writing to file.
        // But usually, we'd default to stdout. The PRD says "the output file can be found in [output file path]".
        std::cerr << "Error: Missing output file path." << std::endl;
        return 0;
    }

    if (!outfile.is_open()) {
        std::cerr << "Error: Could not open output file: " << output_path << std::endl;
        return 0;
    }

    // 1. Print Adjacency Matrix
    outfile << "Adjacency Matrix：" << std::endl;
    outfile << amg << std::endl;

    // 2. Print Adjacency Table
    outfile << "Adjacency Table：" << std::endl;
    outfile << alg << std::endl;

    // 3. DFS (no recursion)
    outfile << "Depth-first search (no recursion) " << std::endl;
    std::vector<int> dfs_res = alg.dfs_noRes();
    for (size_t i = 0; i < dfs_res.size(); ++i) {
        outfile << dfs_res[i] << (i == dfs_res.size() - 1 ? "" : " ");
    }
    outfile << std::endl;

    // 4. BFS
    outfile << "BFS: " << std::endl;
    // Assuming BFS starts from the first vertex in the list
    std::vector<int> bfs_res;
    if (!vex_list.empty()) {
        bfs_res = alg.bfs(vex_list[0]);
    }
    for (size_t i = 0; i < bfs_res.size(); ++i) {
        outfile << bfs_res[i] << (i == bfs_res.size() - 1 ? "" : " ");
    }
    outfile << std::endl;

    outfile.close();

    return 0;
}
