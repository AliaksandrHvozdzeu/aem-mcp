package com.hvozdzeu.core.models;

import org.apache.sling.api.SlingHttpServletRequest;
import org.apache.sling.api.resource.Resource;
import org.apache.sling.models.annotations.DefaultInjectionStrategy;
import org.apache.sling.models.annotations.Model;
import org.apache.sling.models.annotations.injectorspecific.ValueMapValue;

import javax.annotation.PostConstruct;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/**
 * Model for the Key Points component — an ordered/unordered list of points.
 *
 * JCR stores multi-value String[] as a property named "items".
 * If the author stored a comma-separated single String, we split it too.
 */
@Model(
    adaptables = {SlingHttpServletRequest.class, Resource.class},
    defaultInjectionStrategy = DefaultInjectionStrategy.OPTIONAL
)
public class KeyPointsModel {

    @ValueMapValue
    private String title;

    /** Multi-value String property in JCR — AEM stores as String[] */
    @ValueMapValue
    private String[] items;

    /** Optional: "ordered" → <ol>, anything else → <ul> */
    @ValueMapValue
    private String listType;

    private List<String> pointsList;
    private boolean ordered;

    @PostConstruct
    protected void init() {
        if (items != null && items.length > 0) {
            pointsList = Arrays.asList(items);
        } else {
            pointsList = Collections.emptyList();
        }
        ordered = "ordered".equalsIgnoreCase(listType);
    }

    public String getTitle()           { return title; }
    public List<String> getPointsList(){ return pointsList; }
    public boolean isOrdered()         { return ordered; }
    public boolean isHasPoints()       { return !pointsList.isEmpty(); }
}
