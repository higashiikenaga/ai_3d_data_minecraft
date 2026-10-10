package dev.mc3d.ai3d;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Duration;

/** HTTP client for the {@code mc3d serve} job server. All methods block; call them off the main thread. */
public final class GeneratorClient {
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private final String baseUrl;
    private final String apiKey;

    public GeneratorClient(String baseUrl, String apiKey) {
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.apiKey = apiKey == null ? "" : apiKey;
    }

    private HttpRequest.Builder request(String path) {
        HttpRequest.Builder b = HttpRequest.newBuilder(URI.create(baseUrl + path)).timeout(Duration.ofSeconds(30));
        if (!apiKey.isEmpty()) {
            b.header("X-API-Key", apiKey);
        }
        return b;
    }

    private static JsonObject parse(HttpResponse<String> resp) throws IOException {
        JsonObject body;
        try {
            body = JsonParser.parseString(resp.body()).getAsJsonObject();
        } catch (RuntimeException e) {
            throw new IOException("HTTP " + resp.statusCode() + ": " + resp.body());
        }
        if (resp.statusCode() >= 400) {
            String msg = body.has("error") ? body.get("error").getAsString() : resp.body();
            throw new IOException(msg);
        }
        return body;
    }

    public JsonObject submit(JsonObject params) throws IOException, InterruptedException {
        HttpRequest req = request("/jobs")
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(params.toString(), StandardCharsets.UTF_8))
                .build();
        return parse(http.send(req, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)));
    }

    public JsonObject status(String jobId) throws IOException, InterruptedException {
        HttpRequest req = request("/jobs/" + jobId).GET().build();
        return parse(http.send(req, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)));
    }

    public void downloadSchem(String jobId, Path target) throws IOException, InterruptedException {
        HttpRequest req = request("/jobs/" + jobId + "/schem").timeout(Duration.ofMinutes(2)).GET().build();
        Path tmp = target.resolveSibling(target.getFileName() + ".part");
        HttpResponse<Path> resp = http.send(req, HttpResponse.BodyHandlers.ofFile(tmp));
        if (resp.statusCode() != 200) {
            Files.deleteIfExists(tmp);
            throw new IOException("download failed: HTTP " + resp.statusCode());
        }
        Files.move(tmp, target, StandardCopyOption.REPLACE_EXISTING);
    }
}
