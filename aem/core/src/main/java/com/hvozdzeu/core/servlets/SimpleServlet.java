package com.hvozdzeu.core.servlets;

import org.apache.sling.api.SlingHttpServletRequest;
import org.apache.sling.api.SlingHttpServletResponse;
import org.apache.sling.api.resource.Resource;
import org.apache.sling.api.servlets.HttpConstants;
import org.apache.sling.api.servlets.SlingSafeMethodsServlet;
import org.osgi.framework.Constants;
import org.osgi.service.component.annotations.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.servlet.Servlet;
import javax.servlet.ServletException;
import java.io.IOException;
import java.io.PrintWriter;

/**
 * Example Sling Servlet registered by resourceType.
 *
 * How Sling URL resolution works:
 *   URL: /content/mysite/en/page/jcr:content/helloworld.data.json
 *   Sling resolves the resource /content/mysite/en/page/jcr:content/helloworld
 *   Reads its sling:resourceType = "hvozdzeu/components/helloworld"
 *   Looks up the registered servlet matching resourceType + selector + extension
 *   Invokes this servlet → doGet()
 *
 * Registration properties (sling.servlet.*):
 *   resourceTypes — the resource type this servlet is bound to
 *   selectors     — the URL part between the node name and extension (/page.DATA.json)
 *   extensions    — the URL extension (/page.data.JSON)
 *   methods       — HTTP method (GET, POST, etc.)
 *
 * SlingSafeMethodsServlet — base class for read-only servlets (GET, HEAD).
 * For POST/PUT/DELETE use SlingAllMethodsServlet instead.
 */
@Component(
    service = Servlet.class,
    property = {
        Constants.SERVICE_DESCRIPTION + "=hvozdzeu Simple Data Servlet",
        Constants.SERVICE_RANKING + ":Integer=1",
        "sling.servlet.resourceTypes=hvozdzeu/components/helloworld",
        "sling.servlet.selectors=data",
        "sling.servlet.extensions=json",
        "sling.servlet.methods=" + HttpConstants.METHOD_GET
    }
)
public class SimpleServlet extends SlingSafeMethodsServlet {

    private static final long serialVersionUID = 1L;
    private static final Logger LOG = LoggerFactory.getLogger(SimpleServlet.class);

    /**
     * Invoked on a GET request to a resource with selector=data and extension=json.
     *
     * Example URL: /content/mysite/en/page/jcr:content/helloworld.data.json
     *
     * @param request  SlingHttpServletRequest — wraps HttpServletRequest,
     *                 adds getResource(), getResourceResolver(), etc.
     * @param response SlingHttpServletResponse — wraps HttpServletResponse
     */
    @Override
    protected void doGet(
        final SlingHttpServletRequest request,
        final SlingHttpServletResponse response
    ) throws ServletException, IOException {

        // Get the current resource (JCR node being requested)
        final Resource resource = request.getResource();
        LOG.debug("SimpleServlet.doGet() | path={}", resource.getPath());

        // Read properties from the JCR node via ValueMap
        final String message = resource.getValueMap().get("message", "World");
        final String title   = resource.getValueMap().get("jcr:title", "(no title)");

        // Build JSON response manually (no Jackson dependency needed for this example).
        // In a real project use Gson or Jackson with scope=compile.
        response.setContentType("application/json;charset=UTF-8");
        response.setCharacterEncoding("UTF-8");

        // Disable caching (useful during development)
        response.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");

        try (PrintWriter writer = response.getWriter()) {
            writer.printf(
                "{\"status\":\"ok\",\"path\":\"%s\",\"title\":\"%s\",\"message\":\"%s\"}",
                escapeJson(resource.getPath()),
                escapeJson(title),
                escapeJson(message)
            );
        }
    }

    /**
     * Minimal JSON escaping for string values.
     * In production use Jackson ObjectMapper or Gson instead.
     */
    private String escapeJson(final String value) {
        if (value == null) {
            return "";
        }
        return value
            .replace("\\", "\\\\")
            .replace("\"", "\\\"")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t");
    }
}
