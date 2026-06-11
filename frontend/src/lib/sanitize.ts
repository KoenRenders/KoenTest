import DOMPurify from "isomorphic-dompurify";

/**
 * Maakt door admins ingevoerde CMS-HTML veilig vóór het via
 * dangerouslySetInnerHTML te renderen. Verwijdert scripts, event-handlers
 * en javascript:-URLs, maar laat de opmaak toe die de Tiptap-editor maakt
 * (koppen, lijsten, links, vetgedrukt, enz.).
 */
export function sanitizeCmsHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      "p", "br", "strong", "b", "em", "i", "u", "s",
      "h1", "h2", "h3", "h4", "h5", "h6",
      "ul", "ol", "li", "blockquote", "code", "pre",
      "a", "hr",
    ],
    ALLOWED_ATTR: ["href", "target", "rel"],
    // Sta enkel veilige URL-schema's toe in href (geen javascript:).
    ALLOWED_URI_REGEXP: /^(?:https?:|mailto:|tel:|#|\/)/i,
  });
}
