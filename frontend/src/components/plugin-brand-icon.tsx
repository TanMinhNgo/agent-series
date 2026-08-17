import {
  si1password,
  siAirtable,
  siAirbnb,
  siAsana,
  siBehance,
  siBookingdotcom,
  siCloudflare,
  siClickup,
  siCoinbase,
  siCoursera,
  siDatadog,
  siDiscord,
  siDribbble,
  siDropbox,
  siExpedia,
  siFigma,
  siFitbit,
  siFramer,
  siGarmin,
  siGitlab,
  siGithub,
  siGmail,
  siGoogleanalytics,
  siGoogledrive,
  siGooglemaps,
  siHeadspace,
  siHubspot,
  siIntercom,
  siJira,
  siKhanacademy,
  siLinear,
  siLooker,
  siMixpanel,
  siMiro,
  siNetflix,
  siNotion,
  siOkta,
  siPeloton,
  siPosthog,
  siQuickbooks,
  siSentry,
  siShopify,
  siSnyk,
  siSpotify,
  siSteam,
  siStrava,
  siStripe,
  siTodoist,
  siTrello,
  siTripadvisor,
  siTwitch,
  siUdemy,
  siVercel,
  siVirustotal,
  siWise,
  siWolfram,
  siXero,
  siYoutube,
  siZapier,
  siZendesk,
  siZotero,
  siZoom,
} from 'simple-icons';

const catalogLogos = {
  github: siGithub,
  gitlab: siGitlab,
  linear: siLinear,
  vercel: siVercel,
  sentry: siSentry,
  'google-workspace': siGoogledrive,
  notion: siNotion,
  asana: siAsana,
  clickup: siClickup,
  todoist: siTodoist,
  figma: siFigma,
  miro: siMiro,
  framer: siFramer,
  behance: siBehance,
  dribbble: siDribbble,
  hubspot: siHubspot,
  intercom: siIntercom,
  shopify: siShopify,
  jira: siJira,
  zendesk: siZendesk,
  coursera: siCoursera,
  khanacademy: siKhanacademy,
  udemy: siUdemy,
  zotero: siZotero,
  wolfram: siWolfram,
  posthog: siPosthog,
  googleanalytics: siGoogleanalytics,
  mixpanel: siMixpanel,
  looker: siLooker,
  datadog: siDatadog,
  discord: siDiscord,
  zoom: siZoom,
  gmail: siGmail,
  '1password': si1password,
  okta: siOkta,
  cloudflare: siCloudflare,
  snyk: siSnyk,
  virustotal: siVirustotal,
  stripe: siStripe,
  quickbooks: siQuickbooks,
  xero: siXero,
  wise: siWise,
  coinbase: siCoinbase,
  fitbit: siFitbit,
  garmin: siGarmin,
  strava: siStrava,
  headspace: siHeadspace,
  peloton: siPeloton,
  googlemaps: siGooglemaps,
  bookingdotcom: siBookingdotcom,
  airbnb: siAirbnb,
  expedia: siExpedia,
  tripadvisor: siTripadvisor,
  spotify: siSpotify,
  youtube: siYoutube,
  netflix: siNetflix,
  twitch: siTwitch,
  steam: siSteam,
  dropbox: siDropbox,
  trello: siTrello,
  airtable: siAirtable,
  zapier: siZapier,
} as const;

function SlackLogo() {
  return (
    <svg viewBox="0 0 256 256" className="size-6">
      <path
        fill="#e01e5a"
        d="M53.841 161.32c0 14.832-11.987 26.82-26.819 26.82S.203 176.152.203 161.32c0-14.831 11.987-26.818 26.82-26.818H53.84zm13.41 0c0-14.831 11.987-26.818 26.819-26.818s26.819 11.987 26.819 26.819v67.047c0 14.832-11.987 26.82-26.82 26.82c-14.83 0-26.818-11.988-26.818-26.82z"
      />
      <path
        fill="#36c5f0"
        d="M94.07 53.638c-14.832 0-26.82-11.987-26.82-26.819S79.239 0 94.07 0s26.819 11.987 26.819 26.819v26.82zm0 13.613c14.832 0 26.819 11.987 26.819 26.819s-11.987 26.819-26.82 26.819H26.82C11.987 120.889 0 108.902 0 94.069c0-14.83 11.987-26.818 26.819-26.818z"
      />
      <path
        fill="#2eb67d"
        d="M201.55 94.07c0-14.832 11.987-26.82 26.818-26.82s26.82 11.988 26.82 26.82s-11.988 26.819-26.82 26.819H201.55zm-13.41 0c0 14.832-11.988 26.819-26.82 26.819c-14.831 0-26.818-11.987-26.818-26.82V26.82C134.502 11.987 146.489 0 161.32 0s26.819 11.987 26.819 26.819z"
      />
      <path
        fill="#ecb22e"
        d="M161.32 201.55c14.832 0 26.82 11.987 26.82 26.818s-11.988 26.82-26.82 26.82c-14.831 0-26.818-11.988-26.818-26.82V201.55zm0-13.41c-14.831 0-26.818-11.988-26.818-26.82c0-14.831 11.987-26.818 26.819-26.818h67.25c14.832 0 26.82 11.987 26.82 26.819s-11.988 26.819-26.82 26.819z"
      />
    </svg>
  );
}

function TeamsLogo() {
  return (
    <svg viewBox="0 0 256 239" className="size-6">
      <path
        fill="#5059c9"
        d="M178.563 89.302h66.125c6.248 0 11.312 5.065 11.312 11.312v60.231c0 22.96-18.613 41.574-41.573 41.574h-.197c-22.96.003-41.576-18.607-41.579-41.568V95.215a5.91 5.91 0 0 1 5.912-5.913"
      />
      <circle cx="223.256" cy="50.605" r="26.791" fill="#5059c9" />
      <circle cx="139.907" cy="38.698" r="38.698" fill="#7b83eb" />
      <path
        fill="#7b83eb"
        d="M191.506 89.302H82.355c-6.173.153-11.056 5.276-10.913 11.449v68.697c-.862 37.044 28.445 67.785 65.488 68.692c37.043-.907 66.35-31.648 65.489-68.692v-68.697c.143-6.173-4.74-11.296-10.913-11.449"
      />
      <path
        fill="#4d55bd"
        d="M10.913 53.581h109.15c6.028 0 10.914 4.886 10.914 10.913v109.151c0 6.027-4.886 10.913-10.913 10.913H10.913C4.886 184.558 0 179.672 0 173.645V64.495C0 58.466 4.886 53.58 10.913 53.58"
      />
      <path fill="#fff" d="M94.208 95.125h-21.82v59.416H58.487V95.125H36.769V83.599h57.439z" />
    </svg>
  );
}

function SharePointLogo() {
  return (
    <svg viewBox="0 0 24 24" className="size-6 fill-[#0078d4]">
      <path d="M22 13.25q0 1.04-.4 1.95q-.39.9-1.07 1.58t-1.59 1.08q-.91.39-1.94.39q-.64 0-1.27-.16q-.09.83-.46 1.54q-.38.72-.97 1.25q-.58.53-1.33.82q-.76.3-1.59.3q-.91 0-1.71-.35q-.79-.34-1.39-.93q-.59-.59-.93-1.39q-.35-.8-.35-1.7v-.32q.03-.15.05-.31H2.83q-.33 0-.59-.24Q2 16.5 2 16.17V7.83q0-.33.24-.59Q2.5 7 2.83 7h2.95q.12-1.06.61-2q.48-.89 1.24-1.56q.75-.68 1.71-1.06T11.38 2q1.16 0 2.18.44q1.03.45 1.79 1.21t1.21 1.79Q17 6.46 17 7.63v.31q0 .15-.04.31q1.04 0 1.95.39q.92.39 1.59 1.07q.71.67 1.1 1.58q.4.92.4 1.96" />
    </svg>
  );
}

export function PluginBrandIcon({
  slug,
  name,
  size = 'sm',
}: {
  slug?: string;
  name: string;
  size?: 'sm' | 'md';
}) {
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase();
  const icon = slug ? catalogLogos[slug as keyof typeof catalogLogos] : undefined;
  const specialIcon =
    slug === 'slack' ? (
      <SlackLogo />
    ) : slug === 'microsoft-teams' ? (
      <TeamsLogo />
    ) : slug === 'onedrive-sharepoint' ? (
      <SharePointLogo />
    ) : null;
  return (
    <span
      className={`grid ${size === 'md' ? 'size-10' : 'size-10'} shrink-0 place-items-center rounded-lg bg-muted font-semibold text-muted-foreground`}
      aria-hidden="true"
    >
      {icon ? (
        <svg viewBox="0 0 24 24" className="size-6" fill={`#${icon.hex}`}>
          <path d={icon.path} />
        </svg>
      ) : (
        specialIcon || <span className="text-[11px]">{initials}</span>
      )}
    </span>
  );
}
