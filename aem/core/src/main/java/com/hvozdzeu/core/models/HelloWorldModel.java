package com.hvozdzeu.core.models;

import org.apache.sling.api.SlingHttpServletRequest;
import org.apache.sling.api.resource.Resource;
import org.apache.sling.models.annotations.DefaultInjectionStrategy;
import org.apache.sling.models.annotations.Model;
import org.apache.sling.models.annotations.injectorspecific.ValueMapValue;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.annotation.PostConstruct;

/**
 * Example Sling Model for the helloworld component.
 *
 * How Sling Models work:
 *   1. HTL template calls data-sly-use.model="com.hvozdzeu.core.models.HelloWorldModel"
 *   2. Sling creates a model instance by adapting the current Request or Resource
 *   3. Sling injects fields via annotations (@ValueMapValue reads from JCR)
 *   4. The @PostConstruct method is called (like a constructor after injection)
 *   5. HTL accesses model getters via ${model.greeting}
 *
 * adaptables — what can serve as a data source for the model:
 *   SlingHttpServletRequest — when access to request parameters is needed
 *   Resource                — when only JCR node data is needed (no request context)
 *
 * defaultInjectionStrategy = OPTIONAL — if a field is not found in JCR, null is injected
 * (instead of REQUIRED, which throws an exception when the value is missing).
 */
@Model(
    adaptables = {SlingHttpServletRequest.class, Resource.class},
    defaultInjectionStrategy = DefaultInjectionStrategy.OPTIONAL
)
public class HelloWorldModel {

    private static final Logger LOG = LoggerFactory.getLogger(HelloWorldModel.class);

    /**
     * @ValueMapValue reads the "message" property from the component JCR node.
     * If the property is not set in the dialog it will be null (due to OPTIONAL).
     *
     * In JCR this lives at: /content/mysite/page/jcr:content/helloworld/@message
     */
    @ValueMapValue
    private String message;

    /**
     * @ValueMapValue with name — explicitly specifies the JCR property name.
     * Useful when the Java field name differs from the JCR property name.
     */
    @ValueMapValue(name = "jcr:title")
    private String title;

    // Computed field — not injected, built in @PostConstruct
    private String greeting;

    /**
     * @PostConstruct is called after all fields have been injected.
     * Business logic that depends on JCR data is built here.
     */
    @PostConstruct
    protected void init() {
        LOG.debug("HelloWorldModel.init() | message={}, title={}", message, title);
        greeting = "Hello, " + (message != null ? message : "World") + "!";
    }

    /** Available in HTL as ${model.greeting} */
    public String getGreeting() {
        return greeting;
    }

    /** Available in HTL as ${model.message} */
    public String getMessage() {
        return message;
    }

    /** Available in HTL as ${model.title} */
    public String getTitle() {
        return title;
    }
}
