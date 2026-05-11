package com.hvozdzeu.core.models;

import org.apache.sling.api.SlingHttpServletRequest;
import org.apache.sling.api.resource.Resource;
import org.apache.sling.models.annotations.DefaultInjectionStrategy;
import org.apache.sling.models.annotations.Model;
import org.apache.sling.models.annotations.injectorspecific.ValueMapValue;

import javax.annotation.PostConstruct;

/**
 * Model for the Hero component — the main banner at the top of the page.
 * Reads title, subtitle, description from JCR properties.
 */
@Model(
    adaptables = {SlingHttpServletRequest.class, Resource.class},
    defaultInjectionStrategy = DefaultInjectionStrategy.OPTIONAL
)
public class HeroModel {

    @ValueMapValue
    private String title;

    @ValueMapValue
    private String subtitle;

    @ValueMapValue
    private String description;

    @ValueMapValue
    private String badgeText;

    private boolean hasContent;

    @PostConstruct
    protected void init() {
        hasContent = title != null && !title.isEmpty();
    }

    public String getTitle()       { return title; }
    public String getSubtitle()    { return subtitle; }
    public String getDescription() { return description; }
    public String getBadgeText()   { return badgeText; }
    public boolean isHasContent()  { return hasContent; }
}
