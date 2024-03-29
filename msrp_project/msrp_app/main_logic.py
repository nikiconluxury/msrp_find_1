from msrp_app.classes_and_utility import Product, ExcelProcessor, ProductSchema, BrandSettings, SKUManager, SearchEngine, DataFetcher, Logger, Azure
import json
import threading
import os
def split_into_chunks(data, num_chunks):
    """
    Splits the data into a specified number of chunks as evenly as possible.

    :param data: The data to be split. Should be a list or a similar iterable.
    :param num_chunks: The number of chunks to split the data into.
    :return: Yields chunks of the original data.
    """
    # Determine the size of each chunk
    chunk_size = len(data) // num_chunks
    extra = len(data) % num_chunks

    start = 0
    for i in range(num_chunks):
        end = start + chunk_size + (1 if i < extra else 0)
        yield data[start:end]
        start = end


def text_writer(product,thread_number, file_name):
    new_name=f"msrp_app/temp_thread_storage/thread_{thread_number}_{file_name.replace('xlsx','txt')}"
    with open(new_name, 'a') as file:
        file.write(f"{product.excel_row_number}\t{product.prices}\t{product.url}\t{product.source_type}\t{product.seller}\t{product.input_sku}\n")
    
def txt_combiner(file_list):
    all_data = []  # List to store all data from all files
    for file in file_list:
        if os.path.exists(file):
            # Check if the file is empty
            with open(file, 'r') as f:
                for line in f:
                    # Split line by tab and strip to remove leading/trailing whitespace
                    data = [item.strip() for item in line.split('\t')]
                    all_data.append(data)
            os.remove(file)  # Delete the empty file            
    return all_data

def process_data_chunk(user_input_file,data_chunk, brand_settings, user_agents, approved_seller_list, whitelisted_domains, thread_number, azure_processor):
    sku_manager = SKUManager(brand_settings)
    search_engine = SearchEngine(user_agents)
    data_fetcher = DataFetcher()
    for data in data_chunk:
        product = Product(data['sku'], data['brand'])
        product.excel_row_number=data['excel_row_number']
        Logger.log(f"Processing product {product.input_sku}")
        brand_rules = brand_settings.get_rules_for_brand(product.brand)  # Get the brand rules
        if not brand_rules:
            Logger.log(f"{product.input_sku}Brand rules not found for brand {product.brand}")
            continue
        sku_variations = sku_manager.generate_variations(product.input_sku, brand_rules)
        Logger.log(f"{product.input_sku} List of Sku Variations:{sku_variations}")
        
        for index, variation in enumerate(sku_variations):
            query_url = search_engine.create_brand_search_query(variation, brand_settings.get_rules_for_brand(product.brand), index)
            Logger.log(f"{product.input_sku}Query URL:{query_url}, Variation:{variation}")
            
            
            html_content = azure_processor.fetch_target_body_azure(variation, query_url)
            if html_content:
                search_results = data_fetcher.parse_google_results(html_content)
            else:
                Logger.log(f"{product.input_sku}HTML content not found for query {query_url}")
                search_results = None
                
                
                
            if search_results:
                Logger.log(f"{product.input_sku}Search Results:{search_results}")
                filtered_urls = search_engine.filter_urls_by_brand_and_whitelist(search_results, brand_rules, whitelisted_domains)
                if filtered_urls:
                    Logger.log(f"{product.input_sku}Filtered Results:{filtered_urls}")    
                ####! FIX HARD CODE MODSENSE FILTER
                   ###################### 
                                                                                                                ##### filtered_urls[0] LIKE THIS SHOULD BE CHANGED
                    filtered_urls_currency = search_engine.filter_urls_by_currency(['/us/','/en-us/','/us-en/','/us.','modesens.com/product'],filtered_urls)
                    if filtered_urls_currency:
                        #print(f"currency urls{filtered_urls_currency}KKKKKKKKKKKKKKKKKKKKKK")
                        for url in filtered_urls_currency:
                            url_type = str(url[1])
                            url_str = str(url[0])

                            Logger.log(f"{product.input_sku} Type: {url_type} URL: {url_str}")

                            product_html = azure_processor.fetch_target_body_azure(variation, url_str)
                            flag_modesense=False
                            if "modesens" in url_str:
                                flag_modesense=True
                                
                                
                            if product_html:

                                product_schemas = data_fetcher.extract_product_schema(product_html)
                                Logger.log(f"{product.input_sku} Product Schemas:{product_schemas}")
                                if product_schemas:
                                    schema_parser=ProductSchema(product_schemas,flag_modesense)
                                    product_details = schema_parser.parse_product_schemas(product_schemas)
                                    
                                    ## FOR NOW ONLY
                                    if url_type == "brand":
                                        product.source_type = "brand"
                                        Logger.log(f"{product.input_sku} Product Details:{product_details}")
                                        product.set_details(**product_details[0])
                                        Logger.log_product(product)
        
                                    elif url_type == "whitelist":
                                        product.source_type = "whitelist"
                                        for index,product_detail in enumerate(product_details):
                                            Logger.log(f"{product.input_sku} Product Details:{product_details}") 
                                            if product_detail['seller'].lower() ==product.brand.lower() or product_detail['seller'].lower() in approved_seller_list:
                                                product.set_details(**product_details[index])
                                                Logger.log_product(product)
                                        
                                    else:
                                        break    
                                        
                                    if product.is_complete():
                                        if not product.url == url_str:
                                            product.url=f"{url_str}, {product.url}"
                                        ##DataHandler.write_output_data(product, 'output_file_path_6.txt')
                                        Logger.log(f"Details found and saved for product {product.input_sku} at URL: {url} by thread {thread_number}")
                                        Logger.log_product(product)
                                        break
                                    
                    if product.is_complete():
                        text_writer(product,thread_number, user_input_file)
                        Logger.log(f"Product Details: {product_details} found using thread {thread_number}") 
                        Logger.log_product(product)
                        break

        if not product.is_complete():
            Logger.log_product(product)
            Logger.log(f"Details not found for any variation of product {product.input_sku}")
    
def main(user_input_file,user_search_col, user_brand_col, user_destination_col, user_min_row):
    settings = json.loads(open('msrp_app/settings.json').read())
    brand_settings = BrandSettings(settings)
    Logger(user_input_file.strip('.xlsx'))
    user_agents = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                   'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                   'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
                   'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
                   'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
                   'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
                   'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36'] # Replace with actual user agents
    
    
    #azure_urls = ["https://1app-310.azurewebsites.net/api/http_trigger2?code=EIvr4DrCSG9T_6KiyFn4Qd--2miMEsTz_dKU0qwo8H2CAzFuYRji3Q=="]
    #azure_urls = ["https://1app-310.azurewebsites.net/api/http_trigger2?code=EIvr4DrCSG9T_6KiyFn4Qd--2miMEsTz_dKU0qwo8H2CAzFuYRji3Q=="]  # Replace with actual Azure function URL
    azure_urls = ["https://app1-310.azurewebsites.net/api/http_trigger1?code=aaZtl2gHcz_fj4U5tJygFl8CElp-hTBUwuSIwgtPQr2PAzFuSIzPIg=="
                  ,"https://app2-310.azurewebsites.net/api/http_trigger2?code=JqeqA99x6armMWPxEPFJ6p7pfCz8zpZDH48-ND_TkGmGAzFu3sUfqQ=="
                  ,"https://app3-310.azurewebsites.net/api/http_trigger3?code=tUmctK0Rk-SAIvQ-Q82Pp-og0oyB0nH7WPTtOdHHXT-2AzFuwgeYUQ=="
                  , "https://app4-310.azurewebsites.net/api/http_trigger4?code=WibpdysnZf1yGO77qg0JC4ZWz6wH5yrTEHyoWNsIPxbbAzFu52VK6g=="
                  ,"https://app5-310.azurewebsites.net/api/http_trigger5?code=BoRW3aSMoEKlbu3s7nWkeJLwvob0S1LKZDNzUatJH5tAAzFue58J7A=="]
    approved_seller_list=[
         'saks fifth avenue',
         'nordstrom',
         'fwrd',
         'forward',
         'modesens',
         'ssense',
         'net-a-porter'
    ]
    whitelisted_domains = [
        "fwrd.com",
        "modesens.com",
        "saksfifthavenue.com",
        "saksoff5th.com",
        "nordstrom.com",
        "nordstromrack.com"
    ]
    excel_data=ExcelProcessor(user_input_file,user_search_col, user_brand_col, user_destination_col, min_row=user_min_row)
    input_data = excel_data.read_excel()
    azure_processor = Azure(azure_urls, user_agents)
    num_threads = 10  # Adjust as needed
    data_chunks = list(split_into_chunks(input_data, num_threads))
    Logger.log(f"Input Data:{input_data}")
    Logger.log(f"Chunk List:{data_chunks}")
    Logger.log(f"The user entered in the following columns: {user_search_col}, {user_brand_col}, {user_destination_col}, {user_min_row}, the file name is {user_input_file}")
    threads = []
    for thread_number, chunk in enumerate(data_chunks):
        Logger.log(f"Current Chunk:{data_chunks}")
        #process_data_chunk(data_chunk, brand_settings, user_agents, azure_urls, approved_seller_list, whitelisted_domains)
        thread = threading.Thread(
            target=process_data_chunk, 
            args=(user_input_file, chunk, brand_settings, user_agents, approved_seller_list, whitelisted_domains, thread_number, azure_processor)
            )
        threads.append(thread)
        thread.start()

    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    
    # Combine all files into one
    file_list = [f"msrp_app/temp_thread_storage/thread_{thread_number}_{user_input_file.replace('xlsx','txt')}" for thread_number in range(num_threads)]
    output=txt_combiner(file_list)
    Logger.log(f"Final Output:{output}")
    excel_data.write_excel(output)