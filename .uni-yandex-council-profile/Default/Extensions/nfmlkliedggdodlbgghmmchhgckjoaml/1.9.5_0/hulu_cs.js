var switches = {
  "twitch_injection": "enabled",
  "hulu_injection": "enabled",
    "yt_injection": "enabled",
  "spotify_injection": "enabled",
  "spotify_mutify": "enabled",
  "spotify_track_attr": "content_type",
  "spotify_track_attr_value": "AD",
  "spotify_track_id": "file_ids_mp3",
  "yt_mutify": "enabled",
  "forced_exclusions": ["nil"],
  "cssjs": "enabled",
  "custom_dynamic_dnr": [],
  "rules_json": "enabled"
};

function injectScript(filePath) 
{
	if(switches && switches["hulu_injection"])
	{
		//valid variable
		if(switches["hulu_injection"] == "disabled")
		{
			//continue without injection
      return;
		}
	}

  const script = document.createElement('script');
  script.src = chrome.runtime.getURL(filePath);
  //console.log(chrome.runtime.getURL(filePath));
  script.type = 'text/javascript';
  script.onload = () => script.remove();
  (document.head || document.documentElement).appendChild(script);
};

func0();

function func0() 
{
	var url = 'https://blockify.b-cdn.net/switches190.json';

		// Display loading state
		console.log('Fetching data...');
		
		fetch(url, { cache: 'no-cache' })
		  .then(response => {
			// Check if the response is ok (status in the range 200-299)
			if (!response.ok) 
			{
				console.error(response); //throw new Error(`HTTP error! Status: ${response.status}`);
			}
			// Parse the JSON data
			return response.json();
		  })
		  .then(data => {
			// Handle successful data retrieval
			console.log('Data fetched successfully:', data);
			if(data && data["spotify_injection"] && data["cssjs"])
			{
				switches = JSON.parse(JSON.stringify(data));
			}
			
			// Process the data
		  })
		  .catch(error => {
			// Handle any errors that occurred during fetch
			console.error('Fetch error:', error.message);
		  })
		  .finally(() => {
			// Operations to perform regardless of success or failure
			console.log('Fetch operation completed');
			start();
		  });
	
};

function start() 
{
		chrome.storage.local.get(['staticrules'], (result0) => {
			chrome.storage.local.get(['exceptions'], (result) => {
		
			console.log(result0.staticrules);
			if(result0.staticrules != "disabled")
			{
			  console.log(`enabled.`); //partial or complete adblocking enabled -> use css based adblocking as well!
			  //check if manually disabled;

			  var hostname = window.location.hostname;
		
				if(result.exceptions == null || result.exceptions == undefined || result.exceptions == "" || result.exceptions.length == 0)
				{
          injectScript('hulu_utils.js');					  
				  //exceptions list empty: blocking enabled on all websites				  
				}
				else if(hostname && result.exceptions.includes(hostname))
				{
					//included in list of exceptions: ad blocking disabled, don't trigger css adblocking mech.
				}
				else
				{
          injectScript('hulu_utils.js');		
				}  
			} 
			else 
			{
			  //=== disabled for sure
			  console.log(`disabled.`); //adblocking disabled totally -> dont do  adblocking
			}
		}); 
		}); 
};