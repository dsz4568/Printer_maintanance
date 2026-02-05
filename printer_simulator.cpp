#include <iostream>
#include <vector>
#include <cmath>
#include <random>
#include <chrono>
#include <thread>
#include <curl/curl.h>
#include "json.hpp"
#include <iomanip>
#include <future>
#include <mutex>

using json = nlohmann::json;

class PrinterSimulator {
private:
    std::string printer_id;
    std::string model;
    std::string location;
    int total_pages;
    double drum_wear;
    double fuser_temp;
    double toner_level;
    int paper_jams;
    double roller_wear;
    int maintenance_cycles;
    int days_operational;

    std::mt19937 gen;
    std::normal_distribution<> temp_noise;
    std::uniform_real_distribution<> wear_dist;

    const std::vector<std::string> MODELS = {
        "Kyocera Taskalfa 3252ci",
        "Kyocera Taskalfa 4052ci",
        "Kyocera Taskalfa 5052ci",
        "Kyocera Taskalfa 6052ci",
        "Kyocera Taskalfa 2552ci"
    };

    const std::vector<std::string> LOCATIONS = {
        "Biuro Główne - Parter",
        "Biuro Główne - 1. Piętro",
        "Dział Księgowości",
        "Magazyn A",
        "Recepcja",
        "Sala Konferencyjna",
        "Dział IT",
        "Biuro Zarządu"
    };

public:
    PrinterSimulator(std::string id, int seed) :
        printer_id(id),
        total_pages(0),
        drum_wear(0.0),
        fuser_temp(180.0),
        toner_level(100.0),
        paper_jams(0),
        roller_wear(0.0),
        // maintenance_cycles and days_operational are set in the body of the constructor
        gen(seed),
        temp_noise(180.0, 5.0),
        wear_dist(0.0, 1.0)
    {
        // 1. Drawing of the model and location
        std::uniform_int_distribution<> model_dist(0, MODELS.size() - 1);
        std::uniform_int_distribution<> loc_dist(0, LOCATIONS.size() - 1);
        
        model = MODELS[model_dist(gen)];
        location = LOCATIONS[loc_dist(gen)];

        // 2. Random initial wear
        std::uniform_real_distribution<> init_dist(0.0, 30.0);
        drum_wear = init_dist(gen);
        roller_wear = init_dist(gen);
        total_pages = static_cast<int>(drum_wear * 1000);

       // 3. AMENDMENT: Random operating time (days) at startup
       // Each printer starts at a different point in the cycle
        std::uniform_int_distribution<> days_dist(0, 365); 
        days_operational = days_dist(gen);

        // We calculate how many maintenance cycles it has already undergone based on randomly selected days.
        // We assume that maintenance takes place approximately every 40 days (according to the logic in getTelemetry).
        maintenance_cycles = days_operational / 40;
    }

    void simulatePrintJob(int pages) {
        total_pages += pages;
        days_operational++; 

        double drum_wear_rate = (total_pages > 50000) ? 0.015 : 0.008;
        drum_wear += pages * drum_wear_rate * (1.0 + wear_dist(gen) * 0.1);

        toner_level -= pages * 0.05;
        if (toner_level < 0) toner_level = 100.0;

        fuser_temp = temp_noise(gen) + (drum_wear * 0.5);

        double roller_wear_rate = (total_pages > 30000) ? 0.02 : 0.01;
        roller_wear += pages * roller_wear_rate * (1.0 + wear_dist(gen) * 0.15);

        double jam_probability = (roller_wear / 100.0) * 0.1;
        if (wear_dist(gen) < jam_probability) paper_jams++;

        // Reset after maintenance
        if (total_pages > 0 && total_pages % 20000 < pages) performMaintenance();
    }

    void performMaintenance() {
        maintenance_cycles++;
        if (drum_wear > 80) drum_wear = 5.0;
        if (roller_wear > 75) roller_wear = 5.0;
        paper_jams = 0;
        toner_level = 100.0;
        // Uwaga: Nie resetujemy days_operational do zera, bo to całkowity czas życia drukarki.
        // Czas od ostatniej konserwacji jest liczony jako modulo w getTelemetry.
    }

    json getTelemetry() {
        json data = {
            {"printer_id", printer_id},
            {"model", model},
            {"location", location},
            {"timestamp", std::time(nullptr)},
            {"total_pages", total_pages},
            {"drum_wear_percent", std::min(drum_wear, 100.0)},
            {"fuser_temperature", fuser_temp},
            {"toner_level_percent", std::max(toner_level, 0.0)},
            {"paper_jams_count", paper_jams},
            {"roller_wear_percent", std::min(roller_wear, 100.0)},
            {"maintenance_cycles", maintenance_cycles},
            //Here, the modulo makes the days since maintenance different for each printer.
            {"days_since_maintenance", days_operational % 40} 
        };
        return data;
    }

    bool needsMaintenance() {
        return drum_wear > 80 || roller_wear > 75 || paper_jams > 20;
    }
};

size_t WriteCallback(void* contents, size_t size, size_t nmemb, std::string* userp) {
    userp->append((char*)contents, size * nmemb);
    return size * nmemb;
}

bool sendTelemetryBatch(const std::string& url, const std::vector<json>& batch) {
    CURL* curl = curl_easy_init();
    if (!curl) return false;

    json batch_data = {
        {"telemetry_batch", batch},
        {"batch_size", batch.size()}
    };

    std::string response;
    std::string json_str = batch_data.dump();
    struct curl_slist* headers = NULL;
    headers = curl_slist_append(headers, "Content-Type: application/json");

    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_str.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 10L);

    CURLcode res = curl_easy_perform(curl);
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    return res == CURLE_OK;
}

int main(int argc, char* argv[]) {
    const int NUM_PRINTERS = 500;
    const int BATCH_SIZE = 50;
    std::string server_url = "http://localhost:5000/telemetry/batch";

    if (argc > 1) server_url = argv[1];

    std::cout << "╔════════════════════════════════════════════════════════╗\n";
    std::cout << "║   PRINTERS SIMULATOR  KYOCERA (Taskalfa)               ║\n";
    std::cout << "╚════════════════════════════════════════════════════════╝\n";

    std::vector<PrinterSimulator> printers;
    printers.reserve(NUM_PRINTERS);
    for (int i = 1; i <= NUM_PRINTERS; i++) {
        std::string id = "PRINTER_" + std::string(4 - std::to_string(i).length(), '0') + std::to_string(i);
        printers.emplace_back(id, i * 42); // The seed is different for each printer.
    }

    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_int_distribution<> pages_dist(50, 300);

    for (int cycle = 1; cycle <= 200; cycle++) {
        std::cout << "Cykl " << cycle << "...\n";
        std::vector<json> all_telemetry;
        all_telemetry.reserve(NUM_PRINTERS);

        for (auto& printer : printers) {
            printer.simulatePrintJob(pages_dist(gen));
            all_telemetry.push_back(printer.getTelemetry());
        }

        for (size_t i = 0; i < all_telemetry.size(); i += BATCH_SIZE) {
            size_t end = std::min(i + BATCH_SIZE, all_telemetry.size());
            std::vector<json> batch(all_telemetry.begin() + i, all_telemetry.begin() + end);
            sendTelemetryBatch(server_url, batch);
        }
        std::this_thread::sleep_for(std::chrono::seconds(3));
    }
    return 0;
}